// Giai đoạn 2: không xử lý phân quyền ở frontend; backend luôn xác minh lại.
const workState={machines:[],tasks:[],staff:[]};
const $w=id=>document.getElementById(id);
const eW=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function workApi(path,options={}){const r=await fetch('/api/work'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});let data;try{data=await r.json()}catch{data={detail:'Lỗi máy chủ'}}if(!r.ok)throw Error(data.detail||'Lỗi '+r.status);return data}
function workMessage(msg,error=false){const el=$w('workError');if(el){el.textContent=msg;el.style.color=error?'#b91c1c':'#047857'}}

function setMesTenRowScroll(container){
 if(!container)return;
 requestAnimationFrame(()=>{
  const table=container.querySelector('table');
  if(!table)return;
  const rows=[...table.querySelectorAll('tbody tr')];
  container.style.maxHeight='';
  if(rows.length<=10)return;
  const head=table.querySelector('thead');
  const height=(head?.getBoundingClientRect().height||0)+rows.slice(0,10).reduce((sum,row)=>sum+row.getBoundingClientRect().height,0);
  container.style.maxHeight=Math.ceil(height+1)+'px';
 });
}

function staffRankW(position){return /tổ trưởng/i.test(position||'')?0:/kỹ thuật/i.test(position||'')?1:/nhân viên/i.test(position||'')?2:3}
function optW(xs,key,label){return xs.map(x=>`<option value="${eW(x[key])}">${eW(x[label])}</option>`).join('')}
// Chỉ áp dụng kết quả API cho máy đang được chọn; phản hồi cũ không được ghi đè.
let workAssigneesRequestSeq = 0;
async function loadWorkAssignees(){
 const machine=$w('workMachine'), assignee=$w('workAssignee');
 if(!machine||!assignee)return;
 const id=Number(machine.value), requestSeq=++workAssigneesRequestSeq;
 assignee.innerHTML='<option value="">Chọn kỹ thuật viên</option>';
 if(!id)return;
 try{
  const staff=await workApi('/assignees?machine_id='+encodeURIComponent(id));
  if(requestSeq!==workAssigneesRequestSeq||Number(machine.value)!==id)return;
  if(!Array.isArray(staff))throw new Error('Danh sách kỹ thuật viên không hợp lệ');
  assignee.innerHTML='<option value="">Chọn kỹ thuật viên</option>'+staff.map(x=>`<option value="${Number(x.id)}">${eW(x.username)} – ${eW(x.employee_name)}</option>`).join('');
 }catch(e){if(requestSeq===workAssigneesRequestSeq)workMessage(e.message,true);}
}
// Bộ lọc xưởng áp dụng đồng bộ cho nhân viên, máy giao việc và lịch sử.
function workSelectedWorkshop(){return window.currentUser?.role==='team_lead'?'':String($w('workWorkshopFilter')?.value||'');}
function workWorkshopCode(item){return String(item?.workshop_code||'').trim();}
function workWorkshopName(code){const items=[...workState.staff,...workState.machines];const found=items.find(x=>workWorkshopCode(x)===String(code)&&x.workshop_name);return found?String(found.workshop_name):String(code||'—');}
function workVisibleStaff(){const role=window.currentUser?.role, ws=workSelectedWorkshop();return workState.staff.filter(x=>(!ws||workWorkshopCode(x)===ws)&&(role!=='team_lead'||String(x.employee_code).toLowerCase()!==String(window.currentUser?.username||'').toLowerCase())).sort((a,b)=>staffRankW(a.position)-staffRankW(b.position)||String(a.employee_name).localeCompare(String(b.employee_name),'vi'));}
function renderWorkStaff(){const root=$w('teamStaffList');if(!root)return;const visible=workVisibleStaff();root.innerHTML='<table><thead><tr><th>Mã NV</th><th>Họ tên</th><th>Xưởng</th><th>Chức vụ</th></tr></thead><tbody>'+(visible.map(x=>`<tr><td>${eW(x.employee_code)}</td><td><a class="work-person-link" href="#" onclick="showStaffHistory(${Number(x.id)});return false">${eW(x.employee_name)}</a></td><td>${eW(x.workshop_name||workWorkshopName(x.workshop_code))}</td><td>${eW(x.position)}</td></tr>`).join('')||'<tr><td colspan="4">Chưa có nhân viên thuộc xưởng được chọn.</td></tr>')+'</tbody></table>';setMesTenRowScroll(root);}
async function renderWorkMachineSelect(){const sel=$w('workMachine');if(!sel)return;const ws=workSelectedWorkshop(),old=sel.value;const machines=workState.machines.filter(x=>!ws||workWorkshopCode(x)===ws);sel.innerHTML='<option value="">Chọn máy</option>'+machines.map(x=>`<option value="${Number(x.id)}">${eW(x.machine_code)} – ${eW(x.machine_name)}</option>`).join('');sel.value=machines.some(x=>String(x.id)===old)?old:'';await loadWorkAssignees();}
async function onWorkWorkshopChange(){renderWorkStaff();await renderWorkMachineSelect();renderWorkTable();}
function updateWorkWorkshopOptions(){const sel=$w('workWorkshopFilter');if(!sel)return;const prev=sel.value;const codes=[...new Set([...workState.staff,...workState.machines].map(workWorkshopCode).filter(Boolean))].sort();sel.innerHTML='<option value="">Tất cả</option>'+codes.map(x=>`<option value="${eW(x)}">${eW(workWorkshopName(x))}</option>`).join('');sel.value=codes.includes(prev)?prev:'';}
function workLateW(t){
 const due=new Date(t.due_at).getTime();if(!Number.isFinite(due))return false;
 // Chỉ cảnh báo việc còn phải thực hiện; báo cáo đã nộp/duyệt không còn là việc tồn đọng.
 return ['assigned','in_progress','returned'].includes(t.status) && Date.now()>due;
}
function workSoonW(t){const ms=new Date(t.due_at).getTime()-Date.now();return !t.last_submitted_at && ['assigned','in_progress','returned'].includes(t.status) && ms>=0 && ms<=60*60*1000;}
// Trạng thái nghiệp vụ giữ nguyên; nhãn Quá trình hiển thị trong popup Lịch sử.
function workProcessW(t){
 if(t.status==='approved')return {text:'Hoàn thành',css:'work-process-done'};
 if(t.status==='returned')return {text:'Cần kiểm tra lại',css:'work-process-danger'};
 if(t.status==='submitted')return {text:'Chờ duyệt',css:'work-process-pending'};
 if(workLateW(t))return {text:'Quá hạn',css:'work-process-danger'};
 if(workSoonW(t))return {text:'Sắp đến hạn',css:'work-process-soon'};
 return {text:'Đang thực hiện',css:'work-process-active'};
}

const leadStatusLabels={
 pending_lead:'Chờ tiếp nhận',pending_admin:'Chờ Admin duyệt',in_production:'Đang sản xuất',completed:'Đã hoàn thành',rejected:'Từ chối',
 assigned:'Đã giao',in_progress:'Đang thực hiện',submitted:'Chờ duyệt',approved:'Hoàn thành',returned:'Yêu cầu làm lại',
 rejected_by_lead:'Tổ trưởng từ chối',rejected_by_admin:'Admin từ chối'
};
function leadStatusText(v){return leadStatusLabels[String(v||'').toLowerCase()]||({'approve':'Đã duyệt','reject':'Từ chối'}[String(v||'').toLowerCase()])||'Chưa xác định';}
function leadActivityBadge(v){const good=['approved','in_production','completed','approve'].includes(String(v||'').toLowerCase());const bad=['rejected','returned','reject'].includes(String(v||'').toLowerCase());return `<span class="lead-activity-badge ${good?'lead-good':bad?'lead-bad':'lead-neutral'}">${eW(leadStatusText(v))}</span>`;}
async function showLeadActivity(id){
 workDialogOpen({title:'Công việc đã giao',subtitle:'Danh sách công việc Tổ trưởng đã giao cho kỹ thuật viên',content:'<div class="work-dialog-loading">Đang tải công việc...</div>'});
 try {
  const d=await workApi(`/staff/${id}/lead-activity`);
  const overlay=$w('workDialogOverlay');if(!overlay||overlay.hidden)return;
  overlay.querySelector('#workDialogSubtitle').textContent=`${d.employee.employee_name} · ${d.employee.employee_code}`;
  const tasks=d.assigned_tasks||[];
  const time=x=>x?new Date(x).toLocaleString('vi-VN'):'Chưa cập nhật';
  const taskHtml=tasks.map(t=>`<article class="staff-history-card"><div class="staff-history-top"><strong>${eW(t.title)}</strong>${leadActivityBadge(t.status)}</div><div class="staff-history-meta"><span>Máy: ${eW(t.machine_code||'—')}</span><span>Người nhận: ${eW(t.receiver_name||'—')}</span><span>Giao lúc: ${eW(time(t.created_at))}</span><span>Hạn: ${eW(time(t.due_at))}</span></div><div class="staff-history-bottom"><span>Trạng thái: ${eW(leadStatusText(t.status))}</span><button class="work-small-btn" type="button" onclick="showWorkHistory(${Number(t.id)})">Xem báo cáo</button></div></article>`).join('');
  overlay.querySelector('.work-dialog-body').innerHTML=tasks.length?`<div class="staff-history-overview"><strong>${tasks.length}</strong><span>Tổng số công việc đã giao</span></div><section class="staff-history-section"><h3>Công việc đã giao <span>${tasks.length}</span></h3>${taskHtml}</section>`:'<div class="work-empty-history">Tổ trưởng chưa giao công việc nào.</div>';
 }catch(e){const body=$w('workDialogOverlay')?.querySelector('.work-dialog-body');if(body)body.textContent='Không tải được công việc đã giao: '+e.message;}
}

async function showStaffHistory(id){
 workDialogOpen({title:'Công việc được giao',subtitle:'Chi tiết công việc kỹ thuật viên đã nhận',content:'<div class="work-dialog-loading">Đang tải lịch sử...</div>'});
 try{const d=await workApi(`/staff/${id}/history`);const overlay=$w('workDialogOverlay');if(overlay.hidden)return;
  overlay.querySelector('#workDialogSubtitle').textContent=`${d.employee.employee_name} · ${d.employee.employee_code}`;
  const labels={assigned:'Đã giao',in_progress:'Đang làm',submitted:'Chờ tổ trưởng duyệt',approved:'Hoàn thành',returned:'Bị trả lại'};
  const time=x=>x?new Date(x).toLocaleString('vi-VN'):'Chưa cập nhật';
  const taskHtml=d.tasks.map(t=>`<article class="staff-history-card"><div class="staff-history-top"><strong>${eW(t.title)}</strong><span class="work-status ${t.status==='approved'?'work-approved':'work-pending'}">${eW(labels[t.status]||t.status)}</span></div><div class="staff-history-meta"><span>Máy: ${eW(t.machine_code||'—')}</span><span>Giao lúc: ${eW(time(t.created_at))}</span><span>Hạn: ${eW(time(t.due_at))}</span></div>${t.description?`<p class="staff-history-description">${eW(t.description)}</p>`:''}<div class="staff-history-bottom"><span>Quá trình: <span class="work-process-badge ${workProcessW(t).css}">${workProcessW(t).text}</span></span><button class="work-small-btn" type="button" onclick="showWorkHistory(${Number(t.id)})">Xem báo cáo</button></div></article>`).join('');
  overlay.querySelector('.work-dialog-body').innerHTML=taskHtml?`<div class="staff-history-overview"><strong>${d.tasks.filter(t=>t.status==='approved').length}</strong><span>Công việc hoàn thành</span></div><section class="staff-history-section"><h3>Công việc được giao <span>${d.tasks.length}</span></h3>${taskHtml}</section>`:'<div class="work-empty-history">Nhân viên chưa có công việc được giao.</div>';
 }catch(e){const body=$w('workDialogOverlay')?.querySelector('.work-dialog-body');if(body)body.textContent=e.message;}
}
function renderWorkTable(){
 const body=$w('workTable');if(!body)return;
 const search=String($w('workTaskSearch')?.value||'').trim().toLocaleLowerCase('vi-VN');
 const labels={assigned:'Chưa hoàn thành',in_progress:'Đang làm',submitted:'Đã nộp báo cáo',approved:'Hoàn thành',returned:'Bị trả lại'};
 const role=window.currentUser?.role;
 const ws=workSelectedWorkshop();
 const allowedCodes=new Set(workState.machines.filter(m=>workWorkshopCode(m)===ws).map(m=>String(m.machine_code)));
 const allRows=workState.tasks.filter(t=>{
  if(ws && String(t.workshop_code||'')!==ws && !allowedCodes.has(String(t.machine_code)))return false;
  if(!search)return true;
  const haystack=[t.machine_code,t.title,t.description,t.giver_name||t.giver,t.receiver_name||t.receiver,labels[t.status]||t.status,
   new Date(t.created_at).toLocaleString('vi-VN'),new Date(t.due_at).toLocaleString('vi-VN')].join(' ').toLocaleLowerCase('vi-VN');
  return haystack.includes(search);
 }).sort((a,b)=>{
  const priority={returned:0,assigned:1,in_progress:1,submitted:2,approved:9};
  const pa=priority[a.status]??5,pb=priority[b.status]??5;
  return pa-pb||(new Date(b.created_at).getTime()||0)-(new Date(a.created_at).getTime()||0);
 });
 const completed=role==='technician'?allRows.filter(t=>t.status==='approved'):[];
 const rows=role==='technician'?allRows.filter(t=>t.status!=='approved'):allRows;
 if(role==='technician'){
  const completedBody=$w('ktvCompletedTable');
  if(completedBody)completedBody.innerHTML=completed.map(t=>`<tr><td>${eW(t.machine_code)}</td><td><b>${eW(t.title)}</b><div>${eW(t.description)}</div></td><td>${eW(t.giver_name||t.giver)}</td><td>${eW(new Date(t.created_at).toLocaleString('vi-VN'))}</td><td>${eW(new Date(t.due_at).toLocaleString('vi-VN'))}</td><td><span class="work-status work-approved">Hoàn thành</span></td></tr>`).join('')||`<tr><td colspan="6" class="empty">${search?'Không tìm thấy công việc đã làm phù hợp':'Chưa có công việc hoàn thành'}</td></tr>`;
  const finishedCount=$w('ktvCompletedCount');if(finishedCount)finishedCount.textContent=completed.length+' công việc';
 }
 body.innerHTML=rows.map(t=>{
  // Công việc giao ngay là bắt buộc: kỹ thuật viên nộp báo cáo trực tiếp, không cần nhận việc.
  let actions=role==='technician'?'':`<button onclick="showWorkHistory(${t.id})">Lịch sử</button>`;
  if(role==='technician'&&['assigned','in_progress','returned'].includes(t.status))actions=`<button onclick="submitWorkReport(${t.id})">Nộp báo cáo</button>`;
  if(role==='team_lead'&&t.status==='submitted')actions+=` <button onclick="reviewWork(${t.id})">Duyệt / trả lại</button>`;
  const statusText=labels[t.status]||t.status;
  return `<tr><td>${eW(t.machine_code)}</td><td><b>${eW(t.title)}</b><div>${eW(t.description)}</div></td><td>${eW(t.giver_name||t.giver)}</td><td>${eW(t.receiver_name||t.receiver)}</td><td>${eW(new Date(t.created_at).toLocaleString('vi-VN'))}</td><td>${eW(new Date(t.due_at).toLocaleString('vi-VN'))}</td><td><span class="work-status ${t.status==='returned'?'work-returned':t.status==='approved'?'work-approved':''}">${eW(statusText)}</span></td><td>${actions||'—'}</td></tr>`;
 }).join('')||`<tr><td colspan="8">${search?'Không tìm thấy công việc phù hợp':'Chưa có công việc'}</td></tr>`;
 const count=$w('workTaskSearchCount');if(count)count.textContent=search?`Tìm thấy ${rows.length+completed.length}/${workState.tasks.length} công việc`:'';
}

let workLoadRequestSeq = 0;
async function loadWork(){
 const role=window.currentUser?.role;if(!role)return;
 const requestSeq=++workLoadRequestSeq;
 // V79: hide workshop selector for a single-workshop team lead (retain it for Admin).
 const workshopLabel=$w('workWorkshopFilter')?.closest('label');
 if(workshopLabel)workshopLabel.style.display=role==='admin'?'':'none';
 if(role==='team_lead' && $w('workWorkshopFilter'))$w('workWorkshopFilter').value='';
 const heading=$w('workTaskListHeading');
 if(heading)heading.textContent=role==='technician'?'Danh sách công việc chưa hoàn thành':'Danh sách công việc & lịch sử';
 const completedPanel=$w('ktvCompletedPanel');
 if(completedPanel)completedPanel.style.display=role==='technician'?'':'none';
 const workDashboard=$w('workContentDashboard');
 if(role==='technician' && workDashboard){ const list=$w('workTaskListPanel'); if(list && workDashboard.firstElementChild!==list)workDashboard.insertBefore(list,workDashboard.firstElementChild); }
 const assignPanel=$w('workAssignPanel');
 if(assignPanel)assignPanel.style.display=role==='team_lead'?'':'none';
 try{
  const req=[workApi('/tasks')];if(role!=='technician')req.push(workApi('/staff'),workApi('/machines'));
  const data=await Promise.all(req);
  if(requestSeq!==workLoadRequestSeq||window.currentUser?.role!==role)return;
  workState.tasks=data[0];
  if(role!=='technician'){
   const st=data[1];workState.staff=st;
   workState.machines=data[2];
   updateWorkWorkshopOptions();
   if(role==='team_lead')await renderWorkMachineSelect();
  }
  const overdue=data[0].filter(workLateW);
  const alert=$w('workDeadlineAlerts');
  if(alert){const pending=overdue.length;
    alert.hidden=!pending;
    alert.textContent=pending?`⚠ Có ${pending} công việc quá hạn. Vui lòng kiểm tra và xử lý.`:'';
  }
  renderWorkTable();
  // Cập nhật menu cho cả kỹ thuật viên và tổ trưởng theo công việc chưa hoàn thành.
  updateWorkAssignmentDot(data[0],window.currentUser);
  workMessage('');
 }catch(e){if(requestSeq===workLoadRequestSeq)workMessage(e.message,true)}
}
async function submitWork(ev){ev.preventDefault();if(window.currentUser?.role!=='team_lead'){workMessage('Chỉ Tổ trưởng được giao việc',true);return;}try{await workApi('/tasks',{method:'POST',body:JSON.stringify({machine_id:+$w('workMachine').value,assigned_to:+$w('workAssignee').value,title:$w('workTitle').value,description:$w('workDescription').value,due_at:new Date($w('workDue').value).toISOString()})});$w('workAssignForm').reset();await loadWork();workMessage('Đã giao việc thành công')}catch(e){workMessage(e.message,true)}}
async function startWork(id){try{await workApi(`/tasks/${id}/start`,{method:'POST'});await loadWork()}catch(e){workMessage(e.message,true)}}
// Custom accessible dialogs replace browser prompt()/alert() in the work workflow.
let workDialogPreviousFocus = null;
let workDialogBusy = false;
function workDialogClose(){
 const overlay=$w('workDialogOverlay');if(!overlay||workDialogBusy)return;
 overlay.hidden=true;overlay.innerHTML='';document.body.classList.remove('work-dialog-open');
 if(workDialogPreviousFocus?.isConnected)workDialogPreviousFocus.focus();
}
function workDialogOpen({title,subtitle='',content='',footer='',onSubmit=null}){
 const overlay=$w('workDialogOverlay');if(!overlay)throw Error('Thiếu giao diện hộp thoại công việc');
 workDialogPreviousFocus=document.activeElement;workDialogBusy=false;
 overlay.innerHTML=`<section class="work-dialog" role="dialog" aria-modal="true" aria-labelledby="workDialogTitle" aria-describedby="workDialogSubtitle" tabindex="-1">
 <header class="work-dialog-head"><div><h2 id="workDialogTitle">${eW(title)}</h2>${subtitle?`<p id="workDialogSubtitle">${eW(subtitle)}</p>`:''}</div><button class="work-dialog-x" type="button" aria-label="Đóng" data-work-close>×</button></header>
 <form id="workDialogForm"><div class="work-dialog-body">${content}<div class="work-dialog-error" id="workDialogError" role="alert" hidden></div></div><footer class="work-dialog-foot">${footer||'<button class="work-btn work-btn-secondary" type="button" data-work-close>Đóng</button>'}</footer></form></section>`;
 overlay.hidden=false;document.body.classList.add('work-dialog-open');
 overlay.querySelectorAll('[data-work-close]').forEach(b=>b.addEventListener('click',workDialogClose));
 overlay.onclick=(event)=>{if(event.target===overlay)workDialogClose()};
 overlay.onkeydown=(event)=>{
  if(event.key==='Escape'){event.preventDefault();workDialogClose();return;}
  if(event.key==='Tab'){const focusable=Array.from(overlay.querySelectorAll('button:not(:disabled),textarea:not(:disabled),input:not(:disabled),select:not(:disabled)'));
   if(!focusable.length)return;const first=focusable[0],last=focusable[focusable.length-1];
   if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}
 };
 if(onSubmit)overlay.querySelector('#workDialogForm').onsubmit=async(ev)=>{
  ev.preventDefault();if(workDialogBusy)return;
  const form=ev.currentTarget;const submit=form.querySelector('[type="submit"]');const error=$w('workDialogError');
  if(!form.reportValidity())return;
  try{workDialogBusy=true;if(submit){submit.disabled=true;submit.textContent='Đang lưu...'}
   await onSubmit(new FormData(form));workDialogBusy=false;workDialogClose();await loadWork();workMessage('Cập nhật công việc thành công');
  }catch(e){error.hidden=false;error.textContent=e.message||'Không thể lưu thay đổi';}
  finally{workDialogBusy=false;if(submit&&submit.isConnected){submit.disabled=false;submit.textContent=submit.dataset.label||'Xác nhận'}}
 };
 (overlay.querySelector('textarea, input, button[data-work-close]')||overlay.querySelector('.work-dialog')).focus();
}
function taskW(id){return workState.tasks.find(t=>t.id===id)}
function workTaskSubtitle(id){const task=taskW(id);return task?`${task.machine_code} · ${task.title}`:`Công việc #${id}`}
async function submitWorkReport(id){
 workDialogOpen({title:'Nộp báo cáo công việc',subtitle:workTaskSubtitle(id),
 content:`<label class="work-field">Kết quả đã thực hiện <span class="required">*</span><textarea name="summary" required minlength="3" maxlength="10000" rows="4" placeholder="Mô tả công việc đã làm và kết quả đạt được..."></textarea></label><label class="work-field">Lỗi phát sinh (nếu có)<textarea name="errors" maxlength="10000" rows="3" placeholder="Ghi lỗi, nguyên nhân hoặc để trống khi không có"></textarea></label>`,
 footer:`<button type="button" class="work-btn work-btn-secondary" data-work-close>Hủy</button><button class="work-btn work-btn-primary" type="submit" data-label="Gửi báo cáo">Gửi báo cáo</button>`,
 onSubmit:async(form)=>{await workApi(`/tasks/${id}/reports`,{method:'POST',body:JSON.stringify({summary:String(form.get('summary')).trim(),errors:String(form.get('errors')).trim()})})}
 });
}
function reviewWork(id){
 workDialogOpen({title:'Duyệt báo cáo',subtitle:workTaskSubtitle(id),
 content:`<p class="work-dialog-hint">Chọn kết quả duyệt. Nếu trả lại, vui lòng ghi rõ lý do để kỹ thuật viên chỉnh sửa.</p><div class="work-decision-group" role="radiogroup" aria-label="Quyết định"><label class="work-decision"><input type="radio" name="decision" value="approved" checked><span><strong>✓ Duyệt báo cáo</strong><small>Hoàn thành công việc</small></span></label><label class="work-decision"><input type="radio" name="decision" value="returned"><span><strong>↩ Trả lại</strong><small>Yêu cầu làm lại hoặc bổ sung</small></span></label></div><label class="work-field">Nhận xét / lý do trả lại <span id="workCommentRequired" class="required" hidden>*</span><textarea id="workReviewComment" name="comment" maxlength="10000" rows="3" placeholder="Ghi nhận xét cho kỹ thuật viên..."></textarea></label>`,
 footer:`<button type="button" class="work-btn work-btn-secondary" data-work-close>Hủy</button><button type="submit" class="work-btn work-btn-primary" data-label="Xác nhận">Xác nhận</button>`,
 onSubmit:async(form)=>{const decision=String(form.get('decision'));const comment=String(form.get('comment')||'').trim();
 if(decision==='returned'&&!comment)throw Error('Vui lòng nhập lý do trả lại báo cáo.');
 await workApi(`/tasks/${id}/reviews`,{method:'POST',body:JSON.stringify({decision,comment})})}
 });
 const overlay=$w('workDialogOverlay');const comment=$w('workReviewComment');const req=$w('workCommentRequired');
 overlay.querySelectorAll('[name="decision"]').forEach(r=>r.addEventListener('change',()=>{const isReturn=overlay.querySelector('[name="decision"]:checked')?.value==='returned';comment.required=isReturn;req.hidden=!isReturn;comment.placeholder=isReturn?'Nhập lý do yêu cầu chỉnh sửa...':'Ghi nhận xét cho kỹ thuật viên...';}));
}
async function showWorkHistory(id){
 workDialogOpen({title:'Lịch sử công việc',subtitle:workTaskSubtitle(id),content:'<div class="work-dialog-loading">Đang tải lịch sử...</div>'});
 try{
  const arr=await workApi(`/tasks/${id}/history`);const overlay=$w('workDialogOverlay');if(overlay.hidden)return;
  const body=overlay.querySelector('.work-dialog-body');
  const task=workState.tasks.find(t=>Number(t.id)===Number(id));
  const process=task?workProcessW(task):null;
  const processBanner=process?`<div class="work-history-process"><strong>Quá trình</strong><span class="work-process-badge ${process.css}">${eW(process.text)}</span></div>`:"";
  body.innerHTML=processBanner+(arr.length?`<div class="work-timeline">${arr.map((r,i)=>`<article class="work-timeline-item"><div class="work-timeline-card"><div class="work-timeline-top"><strong>Báo cáo ${arr.length-i}</strong><time>${eW(new Date(r.created_at).toLocaleString('vi-VN'))}</time></div><div class="work-history-label">Người báo cáo: ${eW(r.author||'—')}</div><div class="work-history-section"><span>Kết quả công việc</span><p>${eW(r.summary)}</p></div><div class="work-history-section"><span>Lỗi phát sinh</span><p>${eW(r.errors||'Không có')}</p></div><div class="work-history-review"><span class="work-status ${r.decision==='approved'?'work-approved':r.decision==='returned'?'work-returned':'work-pending'}">${r.decision==='approved'?'✓ Đã duyệt':r.decision==='returned'?'↩ Bị trả lại':'Đang chờ duyệt'}</span>${r.reviewer?`<span>${eW(r.reviewer)} · ${eW(new Date(r.reviewed_at).toLocaleString('vi-VN'))}</span>`:''}${r.comment?`<p>${eW(r.comment)}</p>`:''}</div></div></article>`).join('')}</div>`:'<div class="work-empty-history">Chưa có báo cáo nào cho công việc này.</div>');
 }catch(e){const area=$w('workDialogOverlay')?.querySelector('.work-dialog-body');if(area)area.innerHTML=`<div class="work-dialog-error">${eW(e.message)}</div>`;else workMessage(e.message,true)}
}

// Chỉ vai trò nội bộ mới có quyền đọc API công việc.
// Frontend tránh request thừa; Backend vẫn là nơi thực thi phân quyền.
const WORK_DEADLINE_ROLES = new Set(['admin', 'team_lead', 'technician']);
let workDeadlineIntervalId = null;
let workDeadlineStartupId = null;
let workDeadlineRequestInFlight = false;
function workDeadlineAllowed(user = window.currentUser) {
 return !!user && WORK_DEADLINE_ROLES.has(user.role);
}
// Dùng cache theo tài khoản để hiển thị ngay sau reload; API sẽ đồng bộ chính xác.
function workNoticeStorageKey(user=window.currentUser){
 return 'mes-work-pending-count-v5-unfinished:'+String(user?.role||'')+':'+String(user?.username||'').toLowerCase();
}
function showWorkAssignmentCount(count,user=window.currentUser){
 const tab=$w('tabWork');if(!tab)return;
 tab.querySelector('.work-assignment-dot, .work-assignment-count, .work-nav-count')?.remove();
 if(!['technician','team_lead'].includes(user?.role)||!(count>0))return;
 const badge=document.createElement('span');badge.className='work-assignment-count';
 badge.textContent=count>99?'99+':String(count);
 const description=user.role==='team_lead'
  ? `${count} công việc đã giao cho kỹ thuật viên chưa hoàn thành`
  : `${count} công việc chưa hoàn thành cần thực hiện`;
 badge.setAttribute('aria-label',description);
 badge.title=description;
 tab.appendChild(badge);
}
function restoreWorkAssignmentDot(user=window.currentUser){
 let cached=0;
 try{cached=Number(localStorage.getItem(workNoticeStorageKey(user))||'0')}catch(_e){}
 showWorkAssignmentCount(cached,user);
}
function updateWorkAssignmentDot(tasks,user=window.currentUser){
 if(!['technician','team_lead'].includes(user?.role)||!Array.isArray(tasks))return;
 const username=String(user.username||'').trim().toLowerCase();
 // Chỉ loại công việc đã được duyệt hoàn tất (hoặc trạng thái completed).
 // Bao gồm submitted vì báo cáo chưa duyệt thì công việc chưa hoàn thành.
 const unfinished=new Set(['assigned','in_progress','submitted','returned']);
 const count=tasks.filter(task=>{
  if(!unfinished.has(String(task.status||'').toLowerCase()))return false;
  const owner=user.role==='team_lead'?task.giver:task.receiver;
  return String(owner||'').trim().toLowerCase()===username;
 }).length;
 try{localStorage.setItem(workNoticeStorageKey(user),String(count))}catch(_e){}
 showWorkAssignmentCount(count,user);
}
function clearWorkDeadlineBadge() {
 const badge=$w('tabWork')?.querySelector('.work-nav-count');
 if(badge)badge.remove();
 $w('tabWork')?.querySelector('.work-assignment-dot, .work-assignment-count')?.remove();
 const alert=$w('workDeadlineAlerts');
 if(alert){alert.hidden=true;alert.textContent='';}
}
function stopWorkDeadlinePolling(){
 if(workDeadlineIntervalId!==null){clearInterval(workDeadlineIntervalId);workDeadlineIntervalId=null;}
 if(workDeadlineStartupId!==null){clearTimeout(workDeadlineStartupId);workDeadlineStartupId=null;}
 clearWorkDeadlineBadge();
}
async function refreshWorkDeadlineNotice(){
 const user=window.currentUser;
 if(!workDeadlineAllowed(user) || workDeadlineRequestInFlight)return;
 workDeadlineRequestInFlight=true;
 try{
  const tasks=await workApi('/tasks');
  // Bỏ kết quả cũ nếu đăng xuất hoặc chuyển tài khoản khi request đang chạy.
  if(window.currentUser!==user || !workDeadlineAllowed())return;
  if(!Array.isArray(tasks))return;
  updateWorkAssignmentDot(tasks,user);
  const pending=tasks.filter(workLateW).length;
  const soon=tasks.filter(workSoonW).length;
  // Menu chỉ hiển thị số công việc chưa hoàn thành; số quá hạn được nhắc riêng trong trang.
  if(!$w('workView')?.classList.contains('hidden')){
   const alert=$w('workDeadlineAlerts');if(alert){alert.hidden=!pending;alert.textContent=pending?`⚠ Có ${pending} công việc quá hạn cần xử lý.`:'';}
  }
 }catch(_e){} // Không hiển thị lỗi mạng định kỳ lên màn hình đang thao tác.
 finally{workDeadlineRequestInFlight=false;}
}
function startWorkDeadlinePolling(){
 stopWorkDeadlinePolling();
 if(!workDeadlineAllowed())return;
 void refreshWorkDeadlineNotice();
 workDeadlineIntervalId=setInterval(refreshWorkDeadlineNotice,60000);
}
