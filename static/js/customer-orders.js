// Quản lý công đơn khách hàng, xét duyệt, lịch sử và tài khoản khách hàng.
// Classic script: giữ các hàm global để HTML và app.js hiện tại sử dụng.
// ===== Luồng công đơn khách hàng - không sử dụng API Dashboard nội bộ =====
const coStatus = {pending_lead:'Chờ tiếp nhận',pending_admin:'Chờ Admin duyệt',in_production:'Đang sản xuất',completed:'Đã hoàn thành',rejected:'Bị từ chối'};
function coDateTime(value){if(!value)return '—';const d=new Date(value);return Number.isNaN(d.getTime())?'—':d.toLocaleString('vi-VN');}
function coTimeline(o){
 const parts=[`Đã gửi: ${coDateTime(o.created_at)}`];
 if(o.lead_reviewed_at) parts.push(`Tổ trưởng: ${coDateTime(o.lead_reviewed_at)}`);
 else if(o.status==='pending_lead')parts.push('Đang chờ Tổ trưởng tiếp nhận');
 if(o.admin_reviewed_at)parts.push(`Admin: ${coDateTime(o.admin_reviewed_at)}`);
 else if(o.status==='pending_admin')parts.push('Đang chờ Admin duyệt');
 if(o.status==='in_production')parts.push('Đang sản xuất'+(o.order_code?' · '+o.order_code:''));
 if(o.status==='rejected')parts.push('Bị từ chối'+(o.rejection_reason?' · Lý do: '+o.rejection_reason:''));
 return parts.join(' → ');
}
async function loadCustomerOrderOptions(){
 if(window.currentUser?.role!=='customer')return;
 const r=await fetch('/api/customer-orders/options');if(!r.ok)return;
 const data=await r.json();
 for(const [id,arr,label] of [['coWorkshop',data.workshops,'workshop_name'],['coProduct',data.products,'product_name']]){
  const el=document.getElementById(id);el.innerHTML='';
  for(const x of arr){const o=document.createElement('option');o.value=x.id;o.textContent=x[label];el.appendChild(o);}
 }
 document.getElementById('coDate').min=new Date().toLocaleDateString('en-CA');
}
async function customerCreateOrder(ev){
 ev.preventDefault();const v=id=>document.getElementById(id).value;
 const r=await fetch('/api/customer-orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workshop_id:+v('coWorkshop'),product_id:+v('coProduct'),quantity:+v('coFormQuantity'),planned_start:v('coDate'),expected_date:v('coDate'),machine_ids:[]})});
 if(!r.ok)return alert('Không tạo được công đơn: '+await r.text());
 document.getElementById('customerOrderForm').reset();await loadCustomerOrders();alert('Đã gửi công đơn đến tổ trưởng');
}
// Giới hạn bảng công đơn ở tối đa 15 dòng đang hiển thị; vẫn giữ đầy đủ dữ liệu để cuộn và tìm kiếm.
function updateCustomerOrdersScrollHeight(){
 const wrap=document.getElementById('customerOrdersScroll');
 const tbody=document.getElementById('customerOrderRows');
 if(!wrap||!tbody)return;
 // Bỏ chiều cao cũ để đo chiều cao tự nhiên của từng dòng.
 wrap.style.maxHeight='';
 const rows=[...tbody.querySelectorAll('tr[data-customer-order]')].filter(row=>!row.hidden);
 if(rows.length<=15)return;
 const head=wrap.querySelector('thead');
 const headerHeight=head?head.getBoundingClientRect().height:0;
 const fifteenRows=rows.slice(0,15).reduce((height,row)=>height+row.getBoundingClientRect().height,0);
 wrap.style.maxHeight=Math.ceil(headerHeight+fifteenRows+1)+'px';
}
function filterCustomerOrderRows(){
 const input=document.getElementById('customerOrderSearch');
 const body=document.getElementById('customerOrderRows');
 if(!input||!body)return;
 const q=input.value.trim().toLocaleLowerCase('vi-VN');
 const resultColspan=window.currentUser?.role==='technician'?7:9;
 let visible=0;
 body.querySelectorAll('tr[data-customer-order]').forEach(row=>{
  const matched=!q||row.dataset.searchText.includes(q);
  row.hidden=!matched;
  if(matched)visible++;
 });
 let empty=body.querySelector('#customerOrderSearchEmpty');
 if(q && !visible){
  if(!empty){empty=document.createElement('tr');empty.id='customerOrderSearchEmpty';empty.innerHTML=`<td colspan="${resultColspan}" class="empty">Không tìm thấy công đơn phù hợp.</td>`;body.appendChild(empty);}
  empty.hidden=false;
 }else if(empty)empty.remove();
 requestAnimationFrame(updateCustomerOrdersScrollHeight);
}


// Thông báo công đơn chờ xử lý cho Admin, Tổ trưởng và Khách hàng.
// Lưu cache theo tài khoản để không phải đợi API sau khi tải lại trang.
let coNoticeTimer = null;
let coNoticeLoading = false;
function coNoticeKey(user = window.currentUser) {
 return 'mes-order-attention-v2-unfinished:' + String(user?.role || '') + ':' + String(user?.username || '').toLowerCase();
}
function coNoticeSummary(orders, role) {
 // API /api/customer-orders đã lọc phạm vi truy cập của mỗi vai trò.
 // Đếm theo số BẢN GHI công đơn chưa hoàn thành, không đếm tổng sản phẩm
 // và không chỉ đếm các công đơn đang chờ phê duyệt.
 const unfinished = (Array.isArray(orders) ? orders : []).filter(order =>
  ['pending_lead', 'pending_admin', 'in_production'].includes(String(order.status || '').toLowerCase())
 );
 const count = unfinished.length;
 const label = `${count} công đơn chưa hoàn thành`;
 return ['admin', 'team_lead', 'customer'].includes(role)
  ? {count, label}
  : {count: 0, label: ''};
}
function coShowNotice(summary, user = window.currentUser) {
 const tab = document.getElementById('tabDashboard');
 if (!tab) return;
 tab.querySelector('.co-nav-attention-dot, .co-nav-attention-count')?.remove();
 if (!['admin','team_lead','customer'].includes(user?.role) || !(summary?.count > 0)) return;
 const badge = document.createElement('span');
 badge.className = 'co-nav-attention-count';
 badge.textContent = summary.count > 99 ? '99+' : String(summary.count);
 badge.setAttribute('aria-label', summary.label || `${summary.count} công đơn đang chờ xử lý`);
 badge.title = summary.label || `${summary.count} công đơn đang chờ xử lý`;
 tab.appendChild(badge);
}
function coRestoreNotice(user = window.currentUser) {
 if (!['admin','team_lead','customer'].includes(user?.role)) return;
 try {
  const cached = JSON.parse(localStorage.getItem(coNoticeKey(user)) || 'null');
  if (cached) coShowNotice(cached, user);
 } catch (_e) {}
}
function coUpdateNotice(orders, user = window.currentUser) {
 if (!['admin','team_lead','customer'].includes(user?.role) || !Array.isArray(orders)) return;
 const summary = coNoticeSummary(orders, user.role);
 try { localStorage.setItem(coNoticeKey(user), JSON.stringify(summary)); } catch (_e) {}
 coShowNotice(summary, user);
}
async function coPollNotice() {
 const user = window.currentUser;
 if (!['admin','team_lead','customer'].includes(user?.role) || coNoticeLoading) return;
 coNoticeLoading = true;
 try {
  const response = await fetch('/api/customer-orders', {cache:'no-store'});
  if (!response.ok) return;
  const orders = await response.json();
  if (window.currentUser === user) coUpdateNotice(orders, user);
 } catch (_e) { /* Duy trì cache khi mạng tạm thời gián đoạn. */ }
 finally { coNoticeLoading = false; }
}
function coStartNoticePolling(user = window.currentUser) {
 coStopNoticePolling();
 if (!['admin','team_lead','customer'].includes(user?.role)) return;
 coRestoreNotice(user);
 // Dùng cache ngay khi đăng nhập; đồng bộ ngay, không phải đợi chu kỳ đầu tiên.
 void coPollNotice();
 coNoticeTimer = setInterval(coPollNotice, 30000);
}
function coStopNoticePolling() {
 if (coNoticeTimer !== null) { clearInterval(coNoticeTimer); coNoticeTimer = null; }
 document.getElementById('tabDashboard')?.querySelector('.co-nav-attention-dot, .co-nav-attention-count')?.remove();
}

async function loadCustomerOrders(){
 const role=window.currentUser?.role;
 const body=document.getElementById('customerOrderRows');if(!body||!window.currentUser)return;
 const createPanel=document.getElementById('customerOrderCreate');if(createPanel)createPanel.style.display='none';
 const createBtn=document.getElementById('customerCreateOrderBtn');if(createBtn)createBtn.style.display=role==='customer'?'inline-flex':'none';
 try{const r=await fetch('/api/customer-orders');if(!r.ok)throw new Error(await r.text());const rawData=await r.json();
 if(window.currentUser?.role===role) coUpdateNotice(rawData, window.currentUser);
 const statusPriorityByRole={
  admin:{pending_lead:0,pending_admin:1,in_production:2,completed:3,rejected:99},
  team_lead:{pending_lead:0,pending_admin:1,in_production:2,completed:3,rejected:99},
  customer:{rejected:0,pending_lead:1,pending_admin:2,in_production:3,completed:4},
  technician:{pending_lead:0,pending_admin:1,in_production:2,completed:3,rejected:99}
 };
 const statusPriority=statusPriorityByRole[role]||statusPriorityByRole.customer;
 const data=[...(Array.isArray(rawData)?rawData:[])].sort((a,b)=>{
  const aStatus=String(a?.status||'').trim();
  const bStatus=String(b?.status||'').trim();
  // Admin luôn nhìn thấy đơn bị từ chối, nhưng những đơn này phải ở cuối bảng.
  if(role==='admin' && (aStatus==='rejected') !== (bStatus==='rejected'))return aStatus==='rejected'?1:-1;
  const aPriority=Object.prototype.hasOwnProperty.call(statusPriority,aStatus)?statusPriority[aStatus]:8;
  const bPriority=Object.prototype.hasOwnProperty.call(statusPriority,bStatus)?statusPriority[bStatus]:8;
  if(aPriority!==bPriority)return aPriority-bPriority;
  // Đang sản xuất: ưu tiên tiến độ thấp trước để Admin/Tổ trưởng theo dõi.
  if(aStatus==='in_production' && bStatus==='in_production'){
    const progress=order=>Math.max(0,Math.min(100,Number(order.progress_percent)||0));
    const diff=progress(a)-progress(b);
    if(diff!==0)return diff;
  }
  const aDate=Date.parse(a?.expected_date||a?.created_at||0)||0;
  const bDate=Date.parse(b?.expected_date||b?.created_at||0)||0;
  if(aPriority===0||aPriority===1)return aDate-bDate;
  const aId=Number(a?.id)||0;
  const bId=Number(b?.id)||0;
  return bId-aId;
 });
 {
  const sumQuantity = rows => rows.reduce((sum,o)=>sum+(Number(o.quantity)||0),0);
  const quantityTotal = sumQuantity(data);
  const pendingRows = data.filter(o => ['pending_lead','pending_admin'].includes(String(o.status||'')));
  const pendingQuantity = sumQuantity(pendingRows);
  // Đang kế hoạch: tất cả công đơn chưa thực sự đang sản xuất.
  // Bao gồm chờ duyệt, chờ tiếp nhận, kế hoạch và những trạng thái không chạy sản xuất.
  const plannedRows = data.filter(o => !['completed','rejected'].includes(String(o.status||'').trim().toLowerCase()) && !(
    String(o.status || '').trim().toLowerCase() === 'in_production' &&
    !['planned', 'planning'].includes(String(o.production_status || '').trim().toLowerCase())
  ));
  const plannedQuantity = sumQuantity(plannedRows);
  const activeProductionRows = data.filter(o => o.status==='in_production' && !['planned','planning'].includes(String(o.production_status||'').toLowerCase()));
  const activeProductionQuantity = sumQuantity(activeProductionRows);
  const leadPendingCount = data.filter(o=>o.status==='pending_lead').length;
  const adminApprovalRows = data.filter(o => o.status==='pending_admin' || (o.status==='in_production' && Boolean(o.completion_requested_at)));
  const adminPendingCount = adminApprovalRows.length;
  const leadAdminApprovals = data.filter(o=>o.status==='pending_admin');
  const leadAdminCompletions = data.filter(o=>o.status==='in_production' && Boolean(o.completion_requested_at));
  const leadPendingQuantity = sumQuantity(data.filter(o=>o.status==='pending_lead'));
  const adminPendingQuantity = sumQuantity(adminApprovalRows);
  const inProductionCount = data.filter(o=>o.status==='in_production').length;
  const completedRows = data.filter(o=>String(o.status||'').trim().toLowerCase()==='completed');
  const completedQuantity = sumQuantity(completedRows);
  const rejectedCount = data.filter(o=>String(o.status||'').trim().toLowerCase()==='rejected').length;

  const valuesByRole = role === 'customer'
    ? { total:data.length, quantity:quantityTotal, production:sumQuantity(data.filter(o=>o.status==='in_production')), waiting:pendingRows.length }
    : role === 'admin'
      ? { total:quantityTotal, quantity:plannedQuantity, production:activeProductionQuantity, waiting:completedQuantity }
      : { total:data.length, quantity:adminPendingCount, production:inProductionCount, waiting:leadPendingCount };

  for(const [id,n] of [['coTotal',valuesByRole.total],['coQuantity',valuesByRole.quantity],['coProduction',valuesByRole.production],['coWaiting',valuesByRole.waiting]]){
   const el=document.getElementById(id);if(el)el.textContent=Number(n||0).toLocaleString('vi-VN');
  }

  const totalSub = document.getElementById('coTotalSub');
  const quantitySub = document.getElementById('coQuantitySub');
  const productionSub = document.getElementById('coProductionSub');
  const waitingSub = document.getElementById('coWaitingSub');
  if (role === 'admin') {
    if (totalSub) totalSub.textContent = `${data.length.toLocaleString('vi-VN')} công đơn khách hàng`;
    if (quantitySub) quantitySub.textContent = `${plannedRows.length.toLocaleString('vi-VN')} công đơn chưa sản xuất`;
    if (productionSub) productionSub.textContent = `${activeProductionRows.length.toLocaleString('vi-VN')} công đơn đang chạy`;
    if (waitingSub) waitingSub.textContent = `${completedRows.length.toLocaleString('vi-VN')} công đơn đã hoàn thành`;
  } else if (role === 'team_lead') {
    // Gộp số lượng chờ Admin xử lý nhưng PHÂN BIỆT duyệt ban đầu với xác nhận hoàn thành.
    const adminPendingTitle = document.querySelector('#coQuantity')?.previousElementSibling;
    if (adminPendingTitle) adminPendingTitle.textContent =
      leadAdminApprovals.length && leadAdminCompletions.length ? 'Chờ Admin xử lý' :
      leadAdminCompletions.length ? 'Chờ Admin hoàn thành' : 'Chờ Admin duyệt';
    if (totalSub) totalSub.textContent = `Đang sản xuất: ${inProductionCount.toLocaleString('vi-VN')} · Từ chối: ${rejectedCount.toLocaleString('vi-VN')}`;
    if (quantitySub) quantitySub.textContent = `${leadAdminApprovals.length} công đơn chờ duyệt · ${leadAdminCompletions.length} công đơn chờ hoàn thành`;
    if (productionSub) productionSub.textContent = `${sumQuantity(data.filter(o=>o.status==='in_production')).toLocaleString('vi-VN')} sản phẩm thuộc công đơn đang sản xuất`;
    if (waitingSub) waitingSub.textContent = `${leadPendingQuantity.toLocaleString('vi-VN')} sản phẩm thuộc công đơn chờ tiếp nhận`;
  } else {
    if (totalSub) totalSub.textContent = '';
    if (quantitySub) quantitySub.textContent = `${quantityTotal.toLocaleString('vi-VN')} sản phẩm đã tạo`;
    if (productionSub) productionSub.textContent = `${sumQuantity(data.filter(o=>o.status==='in_production')).toLocaleString('vi-VN')} sản phẩm đang chạy`;
    if (waitingSub) waitingSub.textContent = `${pendingRows.length.toLocaleString('vi-VN')} công đơn đang chờ tiếp nhận`;
  }
 }
 body.innerHTML='';for(const o of data){
  const tr=document.createElement('tr');
  const values=[o.order_code||`CD-${String(o.id).padStart(7,"0")}`,o.company_name,o.product_name,o.workshop_name,o.quantity,o.expected_date,(role==='customer' && (o.status==='pending_admin'||o.status==='pending_lead')?'Chờ tiếp nhận':role==='team_lead' && o.status==='rejected'?'Từ chối':coStatus[o.status]||o.status)];
  for(const v of (role==='technician'?values.filter((_,i)=>i!==6):values)){const td=document.createElement('td');td.textContent=v??'—';tr.appendChild(td);}
  const progress=document.createElement('td');
  if(o.status==='rejected') {
    progress.textContent='—';
  } else {
    const percent=Math.max(0,Math.min(100,Number(o.progress_percent)||0));
    const quantity=Number(o.last_stage_quantity)||0;
    const plan=Number(o.quantity)||0;
    const wrap=document.createElement('div');wrap.className='co-progress-wrap';
    const top=document.createElement('div');top.className='co-progress-heading';
    const value=document.createElement('strong');value.textContent=`${percent.toLocaleString('vi-VN',{maximumFractionDigits:2})}%`;
    top.appendChild(value);
    const track=document.createElement('div');track.className='co-progress-track';
    track.setAttribute('role','progressbar');track.setAttribute('aria-valuemin','0');track.setAttribute('aria-valuemax','100');track.setAttribute('aria-valuenow',String(percent));
    track.setAttribute('aria-label',`Tiến độ công đơn ${o.order_code||o.id}`);
    const fill=document.createElement('div');fill.className='co-progress-fill';fill.style.width=`${percent}%`;
    track.appendChild(fill);
    wrap.append(top,track);progress.appendChild(wrap);
  }
  tr.appendChild(progress);
  // Click anywhere on the order row to open history, excluding approval controls.
  tr.dataset.customerOrder='1';
  tr.dataset.searchText=[o.order_code||`CD-${String(o.id).padStart(7,'0')}`,o.company_name,o.product_name,o.workshop_name,o.quantity,o.expected_date,coStatus[o.status]||o.status].map(v=>String(v??'')).join(' ').toLocaleLowerCase('vi-VN');
  tr.classList.add('co-clickable-order');
  tr.tabIndex=0;
  tr.setAttribute('role','button');
  tr.setAttribute('aria-label',`Xem lịch sử công đơn ${o.order_code||'CD-'+String(o.id).padStart(7,'0')}`);
  tr.addEventListener('click',(event)=>{
   if(event.target.closest('button,a,input,select,textarea'))return;
   coOpenHistory(o.id);
  });
  tr.addEventListener('keydown',(event)=>{
   if(event.target!==tr)return;
   if(event.key==='Enter'||event.key===' '){event.preventDefault();coOpenHistory(o.id);}
  });
  if(role!=='technician'){
    const actions=document.createElement('td');
    // Admin chỉ thấy thông báo chờ khi công đơn chưa được Tổ trưởng duyệt.
    // Giữ nguyên quy trình và các nút duyệt của từng vai trò.
    if(role==='admin' && o.status==='pending_lead'){
      const waiting=document.createElement('span');
      waiting.textContent='Chờ được duyệt';
      waiting.style.color='#64748b';
      waiting.style.fontWeight='500';
      waiting.style.whiteSpace='nowrap';
      actions.appendChild(waiting);
    }else if((role==='team_lead'&&o.status==='pending_lead')||(role==='admin'&&o.status==='pending_admin')){
      for(const [action,label] of [[true,'Duyệt'],[false,'Từ chối']]){
        const b=document.createElement('button');b.type='button';b.className='work-small-btn';b.textContent=label;
        b.onclick=(event)=>{event.stopPropagation();customerReview(o.id,action);};actions.appendChild(b);
      }
    }else if((role==='admin'||role==='team_lead') && o.status==='in_production'){
      if(role==='team_lead'){
        if(!o.completion_requested_at){
          const teamActions=document.createElement('div');teamActions.className='co-teamlead-actions';
          const buttonsRow=document.createElement('div');buttonsRow.className='co-teamlead-buttons';
          const edit=document.createElement('button');edit.type='button';edit.className='work-small-btn';
          edit.textContent='Chỉnh sửa';edit.onclick=event=>{event.stopPropagation();coAdminEditProgress(o.id);};
          buttonsRow.appendChild(edit);
          if(Number(o.progress_percent)>=100){
            const submit=document.createElement('button');submit.type='button';submit.className='work-small-btn';
            submit.textContent='Nộp';
            submit.onclick=event=>{event.stopPropagation();coSubmitCustomerCompletion(o.id,o.order_code);};
            buttonsRow.appendChild(submit);
          }
          teamActions.appendChild(buttonsRow);
          if(o.completion_return_reason){
            const note=document.createElement('span');note.className='co-recheck-note';note.textContent='Admin: Kiểm tra lại';
            note.title=o.completion_return_reason;note.setAttribute('aria-label','Admin yêu cầu kiểm tra lại: '+o.completion_return_reason);
            teamActions.appendChild(note);
          }
          actions.appendChild(teamActions);
        }else{
          const pending=document.createElement('span');pending.textContent='Chờ Admin hoàn thành';
          pending.style.color='#a36509';pending.style.fontWeight='700';actions.appendChild(pending);
        }
      }else if(o.completion_requested_at){
        const finish=document.createElement('button');finish.type='button';finish.className='work-small-btn';
        finish.textContent='Hoàn thành';
        finish.onclick=event=>{event.stopPropagation();coCompleteCustomerOrder(o.id,o.order_code);};actions.appendChild(finish);
      }else{
        const pending=document.createElement('span');pending.textContent='Chờ hoàn thành';
        pending.style.color='#64748b';actions.appendChild(pending);
      }
    }else if(role==='customer' && !['in_production','completed'].includes(o.status)){
      // Customers can edit/delete rejected orders and see the rejection reason.
      const customerActions=document.createElement('div');
      customerActions.className='co-customer-actions';
      const buttons=document.createElement('div');buttons.className='co-customer-action-buttons';
      for(const [label,callback] of [['Chỉnh sửa',()=>customerOpenCreateModal(o.id)],['Xóa',()=>customerDeleteOrder(o.id)]]){
        const button=document.createElement('button');button.type='button';button.className='work-small-btn';button.textContent=label;
        button.onclick=event=>{event.stopPropagation();callback();};buttons.appendChild(button);
      }
      customerActions.appendChild(buttons);
      if(o.status==='rejected'){
        const reason=document.createElement('div');
        reason.className='co-customer-rejection';
        const heading=document.createElement('strong');
        heading.textContent='Lý do từ chối:';
        const detail=document.createElement('span');
        detail.textContent=String(o.rejection_reason||'Chưa có lý do được ghi nhận.');
        reason.append(heading,detail);
        customerActions.appendChild(reason);
      }
      actions.appendChild(customerActions);
    }else if(o.status==='completed'){
      const done=document.createElement('span');
      done.textContent='Hoàn thành';
      done.style.color='#16835b';
      done.style.fontWeight='700';
      done.style.whiteSpace='nowrap';
      actions.appendChild(done);
    }else actions.textContent='—';
    tr.appendChild(actions);
  }
  body.appendChild(tr);
 }
 filterCustomerOrderRows();
 const table=body.closest('table');
 if(table){
  const headers=table.querySelectorAll('thead th');
  if(headers[6])headers[6].style.display=role==='technician'?'none':'';
  if(headers[7])headers[7].style.display='';
  if(headers[8])headers[8].style.display=role==='technician'?'none':'';
 }
 if(!data.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=role==='technician'?7:9;td.textContent='Chưa có công đơn';tr.appendChild(td);body.appendChild(tr);}
 const leadBody=document.getElementById('leadCustomerOrderRows');
 if(leadBody && role==='team_lead') {
   leadBody.replaceChildren();
   for(const row of body.querySelectorAll('tr')) {
      const copy=row.cloneNode(true);
      copy.addEventListener('click',event=>{if(!event.target.closest('button'))row.click();});
      copy.addEventListener('keydown',event=>{if(event.target===copy&&(event.key==='Enter'||event.key===' ')){event.preventDefault();row.click();}});
      const originalButtons=row.querySelectorAll('button');
      copy.querySelectorAll('button').forEach((button,index)=>{button.onclick=event=>{event.stopPropagation();originalButtons[index]?.click();};});
      leadBody.appendChild(copy);
   }
 }

 }catch(e){body.textContent='Không tải được công đơn: '+e.message;}
}

// Admin và Tổ trưởng có thể cập nhật sản lượng; chỉ Admin được hoàn thành công đơn.
async function coAdminEditProgress(orderId){
 try{
  const r=await fetch(`/api/customer-orders/${orderId}/production-progress`);
  const data=await r.json().catch(()=>({}));
  if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:`Không tải được công đoạn (${r.status})`);
  const available=data.available_machines||[];
  const stages=(data.stages||[]).map(s=>({machine_id:Number(s.machine_id),quantity_completed:Number(s.quantity_completed||0)}));
  const allowStationChanges = data.allow_station_changes === true;
  const allowStageReorder = data.allow_stage_reorder === true;
  const stageHint = 'Tổ trưởng cập nhật và lưu tiến độ theo các công trạm đã phân công. Khi đạt 100%, quay lại danh sách để Nộp duyệt cho Admin.';
  const html=`<div class="co-admin-progress"><p class="co-progress-hint">Số lượng kế hoạch: <strong>${Number(data.quantity||0).toLocaleString('vi-VN')}</strong> sản phẩm. Cập nhật số lượng đã xử lý theo đúng thứ tự máy.</p>${allowStationChanges?'<div class="co-progress-toolbar"><select id="coStageNew" aria-label="Chọn công trạm chưa được sử dụng"></select><button type="button" class="work-small-btn" id="coStageAdd">+ Thêm công đoạn</button></div>':`<p class="co-progress-hint">${stageHint}</p>`}<section class="co-stage-breakdown"><h4>Phân bổ sản phẩm theo công trạm</h4><p class="co-progress-hint">Biểu đồ chia sản phẩm thành các nhóm không trùng nhau, dựa trên số lượng đã xử lý tại từng công đoạn.</p><div class="co-flow-chart"><div id="coStagePie" class="co-stage-pie co-stage-pie-solid" role="img" aria-label="Phân bổ sản phẩm"></div><div class="co-stage-side"><div class="co-stage-total-card"><span>Kế hoạch</span><strong id="coStagePieTotal"></strong></div><div id="coStageLegend" class="co-stage-legend"></div></div></div></section><h4 class="co-stage-list-heading">Số lượng xử lý theo công đoạn</h4><div id="coStageList"></div></div>`;
  const modal=apModal(`Chỉnh sửa công đơn · CD-${String(orderId).padStart(7,'0')}`,html,async overlay=>{
    const rows=[...overlay.querySelectorAll('[data-stage-machine]')];
    const payload={stages:rows.map(el=>({machine_id:Number(el.dataset.stageMachine),quantity_completed:Number(el.querySelector('input[type="number"]').value)}))};
    if(!payload.stages.length)throw Error('Cần ít nhất một công đoạn');
    if(payload.stages.some(x=>!Number.isInteger(x.quantity_completed)||x.quantity_completed<0||x.quantity_completed>Number(data.quantity)))throw Error('Số lượng phải từ 0 đến số lượng kế hoạch');
    if(payload.stages.some((x,i)=>i>0&&x.quantity_completed>payload.stages[i-1].quantity_completed))throw Error('Số lượng công đoạn sau không được lớn hơn công đoạn trước');
    const response=await fetch(`/api/customer-orders/${orderId}/production-progress`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!response.ok){const err=await response.json().catch(()=>({}));throw Error(typeof err.detail==='string'?err.detail:'Không lưu được công đoạn');}
    await loadCustomerOrders();return true;
  },'Lưu thay đổi');
  modal.querySelector('.ap-modal').classList.add('co-stage-modal');
  const list=modal.querySelector('#coStageList');
  function render(){
    list.replaceChildren();
    stages.forEach((stage,index)=>{
      const machine=available.find(m=>Number(m.id)===stage.machine_id);
      const item=document.createElement('div');item.className='co-stage-edit-row';item.dataset.stageMachine=stage.machine_id;
      const label=document.createElement('div');label.className='co-stage-name';
      const title=document.createElement('div');title.textContent=`${index+1}. ${machine?.machine_code||'MC'} — ${machine?.machine_name||'Công trạm'}`;
      const remainder=document.createElement('small');remainder.className='co-stage-remaining';
      label.append(title,remainder);
      const qty=document.createElement('input');qty.type='number';qty.min='0';qty.max=String(data.quantity);qty.step='1';qty.value=Number(stage.quantity_completed)===0?'':String(stage.quantity_completed);qty.placeholder='0';qty.setAttribute('aria-label',`Số lượng hoàn thành công đoạn ${index+1}`);qty.addEventListener('input',()=>{
        // Chuẩn hóa số lượng ngay khi nhập: 056 -> 56, 000 -> 0.
        // Giữ ô trống trong lúc người dùng đang xóa để nhập số khác.
        if(qty.value!==''){
          const parsed=Number(qty.value);
          if(Number.isFinite(parsed) && parsed>=0 && Number.isInteger(parsed)){
            const normalized=String(parsed);
            if(qty.value!==normalized)qty.value=normalized;
          }
        }
        stage.quantity_completed=qty.value===''?0:Number(qty.value);
        updateRemainders();
      });
      const remove=document.createElement('button');remove.type='button';remove.textContent='Xóa';remove.className='work-small-btn';remove.addEventListener('click',()=>{stages.splice(index,1);render();});
      const up=document.createElement('button');up.type='button';up.textContent='↑';up.disabled=index===0;up.addEventListener('click',()=>{[stages[index-1],stages[index]]=[stages[index],stages[index-1]];render();});
      const down=document.createElement('button');down.type='button';down.textContent='↓';down.disabled=index===stages.length-1;down.addEventListener('click',()=>{[stages[index],stages[index+1]]=[stages[index+1],stages[index]];render();});
      if(allowStationChanges) item.append(label,qty,up,down,remove);
      else if(allowStageReorder) item.append(label,qty,up,down);
      else item.append(label,qty);
      list.appendChild(item);
    });
    updateRemainders();
  }
  function updateRemainders(){
    [...list.querySelectorAll('[data-stage-machine]')].forEach((el,index)=>{
      const before=index===0?Number(data.quantity)||0:Number(stages[index-1].quantity_completed)||0;
      const processed=Number(stages[index].quantity_completed)||0;
      const remaining=before-processed;
      const info=el.querySelector('.co-stage-remaining');
      if(info){
        info.textContent=index===0
          ? `Đã xử lý: ${processed.toLocaleString('vi-VN')} · Chưa xử lý: ${remaining.toLocaleString('vi-VN')}`
          : `Đã xử lý: ${processed.toLocaleString('vi-VN')} · Chưa xử lý tại công đoạn: ${remaining.toLocaleString('vi-VN')}`;
        info.classList.toggle('co-stage-invalid',remaining<0);
      }
    });
    renderDistribution();
  }
  function renderDistribution(){
    const total=Number(data.quantity)||0;
    const fmt=n=>Math.max(0,n).toLocaleString('vi-VN');
    const buckets=[];
    if(stages.length){
      buckets.push({name:'Bắt đầu',amount:total-Number(stages[0].quantity_completed||0)});
      for(let i=1;i<stages.length;i++){
        const completedMachine=available.find(x=>Number(x.id)===stages[i-1].machine_id);
        buckets.push({name:completedMachine?.machine_code||'Công trạm '+i,amount:Number(stages[i-1].quantity_completed||0)-Number(stages[i].quantity_completed||0)});
      }
      // Công trạm cuối cũng phải có dòng chú thích riêng. Sản lượng đã qua
      // công trạm cuối được tính ở nhóm Hoàn thành, không tính hai lần.
      const lastMachine=available.find(x=>Number(x.id)===stages.at(-1).machine_id);
      buckets.push({name:lastMachine?.machine_code||'Công trạm '+stages.length,amount:0});
      buckets.push({name:'Hoàn thành',amount:Number(stages.at(-1).quantity_completed||0)});
    } else buckets.push({name:'Chưa xử lý',amount:total});
    const colors=['#1673CF','#59B9F5','#FF8F7F','#6875E9','#AAB8CC','#F4B84F','#3B9B87','#A57BD1','#7B9CB4'];
    const pie=modal.querySelector('#coStagePie'),legend=modal.querySelector('#coStageLegend');
    if(!pie||!legend)return;
    const safe=buckets.every(x=>Number.isFinite(x.amount)&&x.amount>=0);
    let cursor=0;
    const segments=buckets.map((x,i)=>{const start=cursor;cursor+=total>0?x.amount/total*100:0;return `${colors[i%colors.length]} ${start}% ${cursor}%`;});
    pie.style.background=safe&&total>0?`conic-gradient(${segments.join(',')})`:'#e2e8f0';
    coRenderPiePercentages(pie,buckets,total,safe);
    pie.setAttribute('aria-label',safe?buckets.map(x=>`${x.name}: ${fmt(x.amount)} sản phẩm`).join('; '):'Số lượng công đoạn chưa hợp lệ');
    modal.querySelector('#coStagePieTotal').textContent=fmt(total);
    legend.replaceChildren();
    buckets.forEach((x,i)=>{
      const row=document.createElement('div');row.className='co-stage-legend-row';
      const dot=document.createElement('span');dot.className='co-stage-legend-dot';dot.style.background=colors[i%colors.length];
      const label=document.createElement('span');label.textContent=x.name;
      const value=document.createElement('strong');value.textContent=`${fmt(x.amount)} (${total>0?Math.round(x.amount/total*100):0}%)`;
      row.append(dot,label,value);legend.appendChild(row);
    });
    if(!safe){const error=document.createElement('p');error.className='co-stage-invalid';error.textContent='Số lượng công đoạn sau không được vượt quá công đoạn trước.';legend.prepend(error);}
  }
  if(allowStationChanges){
    const selector=modal.querySelector('#coStageNew');
    const addButton=modal.querySelector('#coStageAdd');
    function updateMachineOptions(){
      selector.replaceChildren();
      for(const m of available.filter(m=>!stages.some(s=>s.machine_id===Number(m.id)))){
        const option=document.createElement('option');
        option.value=String(m.id);
        option.textContent=`${m.machine_code} — ${m.machine_name}`;
        selector.appendChild(option);
      }
      addButton.disabled=!selector.options.length;
    }
    addButton.addEventListener('click',()=>{
      const id=Number(selector.value);
      if(!id||stages.some(s=>s.machine_id===id))return;
      stages.push({machine_id:id,quantity_completed:0});render();updateMachineOptions();
    });
    // Cập nhật dropdown sau cả thao tác xóa công đoạn.
    const originalRender=render;
    // render được gọi từ các nút thay đổi danh sách; cập nhật dropdown sau khi UI ổn định.
    const observer=new MutationObserver(()=>updateMachineOptions());
    observer.observe(list,{childList:true});
    updateMachineOptions();
  }
  render();
 }catch(e){alert(e.message||'Không mở được phần chỉnh sửa');}
}

// Biểu đồ tròn đặc: nhãn phần trăm nằm ngay trên lát cắt, tương tự mẫu tham khảo.
function coRenderPiePercentages(pie, buckets, total, valid){
  if(!pie) return;
  pie.replaceChildren();
  if(!valid || total<=0) return;
  let angle=0;
  buckets.forEach((bucket,index)=>{
    const share=Math.max(0,Number(bucket.amount)||0)/total;
    if(share<=0) return;
    const middle=angle+share*180; // 0 độ ở phía trên, chiều kim đồng hồ
    angle+=share*360;
    // Những lát quá hẹp vẫn có tỷ lệ trong chú giải, tránh chữ chồng lên nhau.
    if(share<0.055) return;
    const theta=(middle-90)*Math.PI/180;
    const radius=share<0.095?37:share<0.15?34:31;
    const label=document.createElement('span');
    label.className='co-pie-percentage';
    // Chữ tối trên các lát sáng, chữ trắng trên các lát tối.
    label.style.color='#FFFFFF';
    label.style.textShadow='0 1px 2px rgba(17,42,79,.24)';
    label.textContent=`${Math.round(share*100)}%`;
    label.style.left=`${50+Math.cos(theta)*radius}%`;
    label.style.top=`${50+Math.sin(theta)*radius}%`;
    label.title=`${bucket.name}: ${Math.round(share*100)}%`;
    pie.appendChild(label);
  });
}

async function coOpenHistory(orderId){
 try{
  const r=await fetch('/api/customer-orders/'+encodeURIComponent(orderId)+'/history');
  if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(typeof e.detail==='string'?e.detail:'Không tải được lịch sử ('+r.status+')');}
  const payload=await r.json(),o=payload.order,stations=payload.stations||[];
  const stationSource=payload.station_source||'recorded';
  const text=v=>safeText(v??'—');
  const line=(label,value)=>`<div class="co-history-field"><span>${text(label)}</span><strong>${text(value)}</strong></div>`;
  const events=[{title:'Khách hàng tạo công đơn',by:o.created_by_username,at:o.created_at,detail:'Công đơn được chuyển đến Tổ trưởng'}];
  if(o.lead_reviewed_at)events.push({title:o.status==='rejected'&&!o.admin_reviewed_at?'Tổ trưởng từ chối':'Tổ trưởng đã xử lý',by:o.lead_username,at:o.lead_reviewed_at,detail:o.admin_reviewed_at||o.status!=='rejected'?'Đã chuyển bước phê duyệt':'Lý do từ chối: '+(o.rejection_reason||'Chưa có lý do được ghi nhận')});
  if(o.admin_reviewed_at)events.push({title:o.status==='rejected'?'Admin từ chối':'Admin phê duyệt',by:o.admin_username,at:o.admin_reviewed_at,detail:o.status==='in_production'?'Đã chuyển sang sản xuất':'Lý do từ chối: '+(o.rejection_reason||'Chưa có lý do được ghi nhận')});
  if(o.completed_at)events.push({title:'Xác nhận hoàn thành công đơn',by:o.completed_by_username,at:o.completed_at,detail:'Đã hoàn thành thủ công sau khi đạt 100%'});
  const stages=events.map((e,i)=>`<div class="co-history-event"><span class="co-history-dot">${i+1}</span><div><strong>${text(e.title)}</strong><div>${text(e.by||'Hệ thống')} · ${coDateTime(e.at)}</div><small>${text(e.detail)}</small></div></div>`).join('');
  // Biểu đồ chỉ xem. Mỗi sản phẩm chỉ được tính trong một nhóm phân bổ.
  const planned=Math.max(0,Number(o.quantity)||0);
  const processed=stations.map(m=>Math.max(0,Number(m.quantity_completed)||0));
  const valid=processed.every((n,i)=>n<=planned&&(i===0||n<=processed[i-1]));
  const fmtQty=n=>Number(n||0).toLocaleString('vi-VN');
  const stationRows=stations.length?stations.map((m,i)=>{
    const count=processed[i];
    const waiting=(i===0?planned:processed[i-1])-count;
    const detail=stationSource==='workshop_reference'?'Công trạm thuộc xưởng (chưa xác nhận tuyến công trạm của công đơn)':(i===0?`Đã xử lý: ${fmtQty(count)} · Chưa xử lý: ${fmtQty(waiting)}`:`Đã xử lý: ${fmtQty(count)} · Chờ xử lý tại công đoạn: ${fmtQty(waiting)}`);
    return `<div class="co-history-station"><span class="co-history-station-number">${i+1}</span><div class="co-history-stage-details"><strong>${text(m.machine_code)} — ${text(m.machine_name)}</strong><small>${detail}</small></div></div>`;
  }).join(''):'<p class="co-history-muted">Chưa có công trạm được ghi nhận.</p>';
  const buckets=[];
  if(stations.length){
    buckets.push({name:'Bắt đầu',amount:planned-processed[0]});
    for(let i=1;i<stations.length;i++)buckets.push({name:stations[i-1].machine_code||`Công trạm ${i}`,amount:processed[i-1]-processed[i]});
    // Đưa công trạm cuối vào chú thích dù sản lượng qua trạm đã nằm ở 'Hoàn thành'.
    // Nhóm này bằng 0 để tổng tỷ lệ luôn bằng 100%, không đếm trùng sản phẩm.
    buckets.push({name:stations.at(-1).machine_code||`Công trạm ${stations.length}`,amount:0});
    buckets.push({name:'Hoàn thành',amount:processed.at(-1)});
  }else buckets.push({name:'Chưa xử lý',amount:planned});
  const colors=['#1673CF','#59B9F5','#FF8F7F','#6875E9','#AAB8CC','#F4B84F','#3B9B87','#A57BD1','#7B9CB4'];
  let cursor=0;
  const segments=buckets.map((b,i)=>{const from=cursor;cursor+=planned>0?b.amount/planned*100:0;return `${colors[i%colors.length]} ${from}% ${cursor}%`;});
  const chartBg=valid&&planned>0?`conic-gradient(${segments.join(',')})`:'#e2e8f0';
  const legend=buckets.map((b,i)=>`<div class="co-stage-legend-row"><span class="co-stage-legend-dot" style="background:${colors[i%colors.length]}"></span><span>${text(b.name)}</span><strong>${fmtQty(b.amount)} (${planned?Math.round(b.amount/planned*100):0}%)</strong></div>`).join('');
  const distribution=stations.length&&stationSource!=='workshop_reference'?`<section class="co-stage-breakdown co-history-breakdown"><h4>Phân bổ sản phẩm theo công trạm</h4><p class="co-progress-hint">${stationSource==='planned'?'Công trạm đã chọn, chưa bắt đầu sản xuất.':'Biểu đồ chia sản phẩm thành các nhóm không trùng nhau, dựa trên số lượng đã xử lý tại từng công đoạn.'}</p><div class="co-flow-chart"><div class="co-stage-pie co-stage-pie-solid" style="background:${chartBg}" role="img" aria-label="Biểu đồ phân bổ sản phẩm"></div><div class="co-stage-side"><div class="co-stage-total-card"><span>Kế hoạch</span><strong>${fmtQty(planned)}</strong></div><div class="co-stage-legend">${valid?legend:'Sản lượng giữa các công đoạn chưa nhất quán. Vui lòng kiểm tra thứ tự và số lượng đã lưu.'}</div></div></div></section>`:'';
  const showTimeline=window.currentUser?.role==='admin'; // Chỉ Admin được xem nhật ký phê duyệt
  const timelineSection=showTimeline?`<h4>Tiến trình xử lý</h4><div class="co-history-events">${stages}</div>`:'';
  const html=`<div class="co-history-wrap"><div class="co-history-summary">${line('Công ty',o.company_name)}${line('Xưởng',o.workshop_name)}${line('Sản phẩm',(o.product_code?o.product_code+' — ':'')+o.product_name)}${line('Số lượng kế hoạch',fmtQty(planned))}${line('Người tạo',o.created_by_name||o.created_by_username||'Chưa ghi nhận')}${line('Ngày tạo đơn',o.created_at?coDateTime(o.created_at):'Chưa ghi nhận')}${line('Ngày bắt đầu',o.production_started_at?coDateTime(o.production_started_at):'Chưa bắt đầu')}${line('Ngày hoàn thành thực tế',o.completed_at?coDateTime(o.completed_at):'Chưa hoàn thành')}${line('Ngày kết thúc (Yêu cầu khách)',o.expected_date?displayDate(o.expected_date):'Chưa có kế hoạch')}${line('Trạng thái',coStatus[o.status]||o.status)}</div>${timelineSection}${o.rejection_reason?`<p class="co-history-reason"><strong>${text(o.status==='rejected'&&!o.admin_reviewed_at?'Lý do Tổ trưởng từ chối:':o.status==='rejected'?'Lý do Admin từ chối:':'Lý do từ chối:')}</strong> ${text(o.rejection_reason)}</p>`:''}${o.completion_return_reason?`<p class="co-history-reason"><strong>Admin yêu cầu kiểm tra lại:</strong> ${text(o.completion_return_reason)}</p>`:''}${distribution}<h4>${stationSource==='workshop_reference'?'Công trạm tham khảo của xưởng':'Công trạm sản xuất'} · ${stations.length} công đoạn</h4>${stationSource==='workshop_reference'?'<p class="co-history-muted">Công đơn cũ chưa lưu danh sách công trạm đã chọn; đây là các máy thuộc xưởng, không phải tuyến công trạm được xác nhận.</p>':''}<div class="co-history-stations">${stationRows}</div></div>`;
  const modal=apModal('Lịch sử công đơn · CD-'+String(o.id).padStart(7,'0'),html,null);
  modal.querySelector('.ap-modal').classList.add('co-history-modal');
  if(stations.length&&stationSource!=='workshop_reference')coRenderPiePercentages(modal.querySelector('.co-history-breakdown .co-stage-pie'),buckets,planned,valid);
 }catch(e){alert(e.message||'Không thể tải lịch sử công đơn');}
}
// V75: team-lead completion submission uses custom teal confirmation modal (no window.confirm).
async function coSubmitCustomerCompletion(id, code){
 const orderCode=code||'CD-'+String(id).padStart(7,'0');
 const content=`<div class="co-review-message"><span class="co-review-symbol" aria-hidden="true">✓</span><p>Bạn có chắc muốn gửi công đơn <strong>${esc(orderCode)}</strong> lên Admin xác nhận hoàn thành không?</p></div>`;
 const modal=apModal('Xác nhận nộp công đơn',content,async ()=>{
  const response=await fetch(`/api/customer-orders/${encodeURIComponent(id)}/submit-completion`,{method:'POST'});
  if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.detail||'Không nộp duyệt được công đơn');}
  await loadCustomerOrders();
  if(typeof loadDashboard==='function')await loadDashboard();
  return true;
 },'Nộp');
 modal.querySelector('.ap-modal')?.classList.add('co-review-modal','co-review-approve');
 return modal;
}
// Admin chỉ xác nhận hoàn thành sau khi Tổ trưởng nộp đủ 100%.
async function coCompleteCustomerOrder(id, code){
 const orderCode=code||'CD-'+String(id).padStart(7,'0');
 const body=`<div class="co-review-message"><span class="co-review-symbol" aria-hidden="true">✓</span><p>Bạn có chắc muốn xác nhận <strong>hoàn thành</strong> công đơn <strong>${esc(orderCode)}</strong> không?</p></div>`;
 const modal=apModal('Xác nhận hoàn thành công đơn',body,async ()=>{
  const response=await fetch(`/api/customer-orders/${encodeURIComponent(id)}/complete`,{method:'POST'});
  if(!response.ok){
   const error=await response.json().catch(()=>({}));
   throw Error(typeof error.detail==='string'?error.detail:'Không hoàn thành được công đơn');
  }
  await loadCustomerOrders();
  if(typeof loadDashboard==='function')await loadDashboard();
  return true;
 },'Hoàn thành');
 modal.querySelector('.ap-modal')?.classList.add('co-review-modal','co-review-approve');
 return modal;
}
function coOrderReviewDialog(id,approve){
  const title=approve?'Xác nhận duyệt công đơn':'Xác nhận từ chối công đơn';
  const message=approve?'Bạn có chắc muốn duyệt công đơn này không?':'Vui lòng nhập lý do từ chối để khách hàng biết và chỉnh sửa công đơn.';
  const content=`<div class="co-review-message"><span class="co-review-symbol" aria-hidden="true">${approve?'✓':'!'}</span><p>${message}</p></div>`+
    (approve?'':'<label class="co-review-label" for="coReviewReason">Lý do từ chối <span aria-hidden="true">*</span></label><textarea class="ap-modal-input co-review-reason" id="coReviewReason" rows="4" maxlength="2000" placeholder="Nhập lý do cụ thể để khách hàng biết cần chỉnh sửa gì..." required></textarea>');
  const modal=apModal(title,content,async overlay=>{
    const reason=approve?'':(overlay.querySelector('#coReviewReason')?.value||'').trim();
    if(!approve && !reason){
      overlay.querySelector('.ap-modal-error').textContent='Bạn cần nhập lý do từ chối công đơn.';
      overlay.querySelector('#coReviewReason')?.focus();return false;
    }
    const r=await fetch(`/api/customer-orders/${encodeURIComponent(id)}/review`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({approve,reason})
    });
    if(!r.ok){
      const error=await r.json().catch(()=>({}));
      throw Error(typeof error.detail==='string'?error.detail:`Không xử lý được công đơn (${r.status})`);
    }
    await loadCustomerOrders();
    return true;
  },approve?'Duyệt':'Từ chối');
  modal.querySelector('.ap-modal').classList.add('co-review-modal',approve?'co-review-approve':'co-review-reject');
  if(!approve)modal.querySelector('#coReviewReason')?.focus();
  return modal;
}
async function customerReview(id,approve){
  coOrderReviewDialog(id,approve);
}

function customerDeleteOrder(orderId){
 const code='CD-'+String(orderId).padStart(7,'0');
 const body=`<div class="co-review-message co-delete-message"><span class="co-review-symbol" aria-hidden="true">!</span><div class="co-delete-description"><p>Bạn có chắc muốn xóa công đơn <strong>${safeText(code)}</strong> không?</p><p class="co-delete-note">Công đơn sẽ không còn xuất hiện trong danh sách, nhưng lịch sử vẫn được lưu để kiểm tra.</p></div></div>`;
 const overlay=apModal('Xác nhận xóa công đơn',body,async modal=>{
   const response=await fetch(`/api/customer-orders/${encodeURIComponent(orderId)}`,{method:'DELETE'});
   if(!response.ok){
     const payload=await response.json().catch(()=>({}));
     throw Error(typeof payload.detail==='string'?payload.detail:'Xóa công đơn thất bại ('+response.status+')');
   }
   await loadCustomerOrders();
   return true;
 },'Xóa công đơn');
 overlay.querySelector('.ap-modal').classList.add('co-review-modal','co-delete-modal');
 // Hủy/đóng không gửi yêu cầu xóa. Esc cũng chỉ đóng modal này.
 const cancelButton=overlay.querySelector('.ap-modal-footer .ap-modal-close');
 const handleKey=e=>{
   if(e.key==='Escape'){
     e.preventDefault();
     overlay.remove();
     document.removeEventListener('keydown',handleKey);
   }
 };
 document.addEventListener('keydown',handleKey);
 const cleanup=new MutationObserver(()=>{
   if(!overlay.isConnected){document.removeEventListener('keydown',handleKey);cleanup.disconnect();}
 });
 cleanup.observe(document.body,{childList:true});
 cancelButton?.focus();
 return overlay;
}

async function customerOpenCreateModal(editOrderId=null){
 if(window.currentUser?.role!=='customer')return;
 let data;
 try { const r=await fetch('/api/customer-orders/options');if(!r.ok)throw Error(await r.text());data=await r.json(); }
 catch(e){return alert('Không tải được lựa chọn: '+e.message);}
 let existing=null;let existingStations=[];
 if(editOrderId){try{const response=await fetch(`/api/customer-orders/${editOrderId}/history`);if(!response.ok)throw Error('Không tải được công đơn');const detail=await response.json();existing=detail.order;existingStations=detail.stations||[];}catch(error){return alert(error.message);}}
 const options=(arr,label)=>arr.map(x=>`<option value="${Number(x.id)}">${safeText(x[label])}</option>`).join('');
 const today=new Date().toLocaleDateString('en-CA');
 const html=`<div class="po-form-grid">
 <label>Mã công đơn<input name="order_code" value="${existing?'CD-'+String(editOrderId).padStart(7,'0'):'Tự động cấp sau khi tạo công đơn'}" disabled></label>
 <label>Xưởng *<select name="workshop_id" required><option value="">Chọn phân xưởng</option>${options(data.workshops,'workshop_name')}</select></label>
 <label>Sản phẩm *<select name="product_id" required disabled><option value="">Chọn xưởng trước</option></select></label>
 <label>Số lượng kế hoạch *<input name="quantity" type="number" min="1" max="100000000" required placeholder="Nhập số lượng sản phẩm"></label>
 <label>Ngày bắt đầu dự kiến *<input name="planned_start" type="date" min="${today}" value="${today}" required></label>
 <label>Ngày kết thúc dự kiến *<input name="expected_date" type="date" min="${today}" value="${today}" required></label>
 <label>Trạng thái ban đầu<input value="Chờ tiếp nhận" disabled></label>
 <section class="co-station-section" aria-label="Công trạm sản xuất">
   <h4 class="co-station-heading">Công trạm sản xuất <span class="co-required-star" aria-label="bắt buộc">*</span></h4>
   <div class="co-station-columns">
     <div class="co-station-card">
       <div class="co-station-card-head">Danh sách công trạm sản xuất</div>
       <label class="co-station-search-label"><span aria-hidden="true">⌕</span><input type="search" id="coStationSearch" placeholder="Tìm công trạm..." aria-label="Tìm công trạm sản xuất"></label>
       <div id="coMachines" class="co-station-list"></div>
     </div>
     <div class="co-station-card">
       <div class="co-sequence-head"><strong id="coSequenceCount">Thứ tự thực hiện (0 công đoạn)</strong><button type="button" id="coClearStations" class="co-clear-stations">Xóa tất cả</button></div>
       <div id="coMachineSequence" class="co-machine-sequence" aria-live="polite"></div>
       <p class="co-sequence-help">ⓘ Chọn công trạm và sắp xếp thứ tự thực hiện theo quy trình sản xuất.</p>
     </div>
   </div>
 </section>
 <p class="po-form-hint">Mã công đơn sẽ được hệ thống cấp ngay khi lưu thành công, ví dụ CD-0000001. Bạn sẽ thấy mã trong danh sách công đơn. Sản phẩm chỉ hiển thị theo xưởng đã chọn.</p></div>`;
 const modal=apModal(editOrderId?'Chỉnh sửa công đơn':'Tạo công đơn',html,async(el)=>{
  const value=n=>el.querySelector(`[name="${n}"]`)?.value||'';
  if(!value('workshop_id')||!value('product_id'))throw Error('Vui lòng chọn xưởng và sản phẩm phù hợp');
  if(!value('quantity')||!value('planned_start')||!value('expected_date'))throw Error('Nhập đủ số lượng, ngày bắt đầu và ngày kết thúc');
  if(value('planned_start')>value('expected_date'))throw Error('Ngày kết thúc phải từ ngày bắt đầu kế hoạch');
  const machine_ids=[...selectedMachines];
  if(!machine_ids.length)throw Error('Chọn ít nhất một công trạm sản xuất');
  const payload={workshop_id:+value('workshop_id'),product_id:+value('product_id'),quantity:+value('quantity'),planned_start:value('planned_start'),expected_date:value('expected_date'),machine_ids};
  const r=await fetch(editOrderId?`/api/customer-orders/${editOrderId}`:'/api/customer-orders',{method:editOrderId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r.ok){const body=await r.json().catch(()=>({}));throw Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||body));}
  const created=await r.json();
  await loadCustomerOrders();
  const successBody = editOrderId
    ? `<div class="co-save-success"><div class="co-save-success-icon" aria-hidden="true">✓</div><h4>Cập nhật công đơn thành công</h4><p>Thông tin công đơn đã được lưu. Công đơn ở trạng thái <strong>Chờ tiếp nhận</strong> để Tổ trưởng xét duyệt.</p></div>`
    : `<div class="co-save-success"><div class="co-save-success-icon" aria-hidden="true">✓</div><h4>Tạo công đơn thành công</h4><p>Mã công đơn: <strong>${safeText(created.order_code)}</strong></p><p>Trạng thái: <strong>Chờ tiếp nhận</strong>.</p></div>`;
  const successModal=apModal('Thông báo',successBody,null);
  successModal.querySelector('.ap-modal')?.classList.add('co-success-modal');
  // Đây là thông báo thành công, không phải bước xác nhận: tự đóng sau 4 giây.
  // Giữ nút X để người dùng chủ động đóng sớm khi cần.
  successModal.querySelector('.ap-modal-footer')?.remove();
  setTimeout(() => { if(successModal.isConnected) successModal.remove(); }, 4000);
  return true;
 },editOrderId?'Lưu thay đổi':'Tạo công đơn');
 modal.querySelector('.ap-modal').classList.add('co-create-modal');
 const workshop=modal.querySelector('[name="workshop_id"]');
 const product=modal.querySelector('[name="product_id"]');
 const machines=modal.querySelector('#coMachines');
 const sequence=modal.querySelector('#coMachineSequence');
 const selectedMachines=[];
 const machineInfo=new Map((data.machines||[]).map(m=>[Number(m.id),m]));
 const stationSearch=modal.querySelector('#coStationSearch');
 const sequenceCount=modal.querySelector('#coSequenceCount');
 const clearStations=modal.querySelector('#coClearStations');
 let availableMachines=[];
 const renderSequence=()=>{
  sequenceCount.textContent=`Thứ tự thực hiện (${selectedMachines.length} công đoạn)`;
  clearStations.disabled=!selectedMachines.length;
  sequence.innerHTML=selectedMachines.length ? selectedMachines.map((id,index)=>{
   const m=machineInfo.get(id)||{};
   return `<div class="co-sequence-step" data-machine-id="${id}">
     <span class="co-step-index">${index+1}</span>
     <span class="co-step-name"><b>${safeText(m.machine_code||'')}</b><small>${safeText(m.machine_name||'')}</small></span>
     <div class="co-step-actions"><button type="button" data-dir="up" data-index="${index}" aria-label="Đưa công đoạn ${index+1} lên" title="Chuyển lên" ${index===0?'disabled':''}>↑</button><button type="button" data-dir="down" data-index="${index}" aria-label="Đưa công đoạn ${index+1} xuống" title="Chuyển xuống" ${index===selectedMachines.length-1?'disabled':''}>↓</button><button type="button" class="co-step-remove" data-remove="${id}" aria-label="Bỏ công trạm ${safeText(m.machine_code||'')}" title="Bỏ công trạm">×</button></div>
    </div>`;
  }).join('') : '<div class="co-station-empty">Chưa chọn công trạm.<br>Chọn công trạm từ danh sách bên trái.</div>';
 };
 const renderAvailable=()=>{
  const search=stationSearch.value.trim().toLocaleLowerCase('vi');
  const filtered=availableMachines.filter(m=>(m.machine_code+' '+m.machine_name).toLocaleLowerCase('vi').includes(search));
  machines.innerHTML=filtered.map(m=>`<label class="co-station-option ${selectedMachines.includes(Number(m.id))?'is-selected':''}"><input type="checkbox" name="co_machine" value="${Number(m.id)}" ${selectedMachines.includes(Number(m.id))?'checked':''}><span><b>${safeText(m.machine_code)}</b> — ${safeText(m.machine_name)}</span></label>`).join('')||'<p class="co-station-empty">Không tìm thấy công trạm phù hợp.</p>';
 };
 machines.addEventListener('change',(event)=>{
  const input=event.target.closest('input[name="co_machine"]');if(!input)return;
  const id=Number(input.value);const index=selectedMachines.indexOf(id);
  if(input.checked&&index<0)selectedMachines.push(id);
  if(!input.checked&&index>=0)selectedMachines.splice(index,1);
  renderAvailable();renderSequence();
 });
 stationSearch.addEventListener('input',renderAvailable);
 clearStations.addEventListener('click',()=>{selectedMachines.length=0;renderAvailable();renderSequence();});
 sequence.addEventListener('click',(event)=>{
  const remove=event.target.closest('button[data-remove]');
  if(remove){const idx=selectedMachines.indexOf(Number(remove.dataset.remove));if(idx>=0)selectedMachines.splice(idx,1);renderAvailable();renderSequence();return;}
  const btn=event.target.closest('button[data-dir]');if(!btn)return;
  const index=Number(btn.dataset.index);const next=index+(btn.dataset.dir==='up'?-1:1);
  if(next<0||next>=selectedMachines.length)return;
  [selectedMachines[index],selectedMachines[next]]=[selectedMachines[next],selectedMachines[index]];
  renderSequence();
 });
 const updateProducts=()=>{
  const id=Number(workshop.value);
  const matches=(data.products||[]).filter(x=>Number(x.workshop_id)===id);
  product.innerHTML='<option value="">'+(id?(matches.length?'Chọn sản phẩm thuộc xưởng':'Xưởng chưa có sản phẩm được cấu hình'):'Chọn xưởng trước')+'</option>'+matches.map(x=>`<option value="${Number(x.id)}">${safeText(x.product_code)} — ${safeText(x.product_name)}</option>`).join('');
  product.disabled=!matches.length;
  selectedMachines.length=0;
  availableMachines=(data.machines||[]).filter(m=>Number(m.workshop_id)===id);
  stationSearch.value='';renderAvailable();renderSequence();
 };
 workshop.addEventListener('change',updateProducts);
 if(existing){workshop.value=String(existing.workshop_id);}
 updateProducts();
 if(existing){
   product.value=String(existing.product_id);
   modal.querySelector('[name="quantity"]').value=existing.quantity;
   for(const station of existingStations){const match=(data.machines||[]).find(m=>m.machine_code===station.machine_code);if(match && Number(match.workshop_id)===Number(existing.workshop_id))selectedMachines.push(Number(match.id));}
   renderAvailable();renderSequence();
 }
}

function customerApiError(error, status){
 const details=error?.detail ?? error?.message ?? error;
 if(Array.isArray(details)) return details.map(x=>typeof x==='string'?x:(x?.msg||JSON.stringify(x))).join('; ');
 if(typeof details==='string')return details;
 if(details&&typeof details==='object')return details.msg||details.message||JSON.stringify(details);
 return `Không thể tạo tài khoản (HTTP ${status}). Kiểm tra Terminal Python.`;
}
async function openNewCustomerAccount(){
 if(window.currentUser?.role!=='admin')return;
 const passwordField=(name,label)=>`<label style="display:block">${label} *<div class="customer-password-row"><input class="search" name="${name}" minlength="12" maxlength="128" required type="password" autocomplete="new-password" placeholder="${label}" style="width:100%;min-width:0;flex:1"><button type="button" class="customer-password-eye" data-for="${name}" aria-label="Hiện ${label.toLowerCase()}" aria-pressed="false" title="Hiện/ẩn ${label.toLowerCase()}">👁 Hiện</button></div></label>`;
 const html=`<form id="newCustomerForm" style="display:grid;gap:14px" autocomplete="off">
   <label>Tên công ty *<input class="search" name="company_name" minlength="2" maxlength="200" required placeholder="Ví dụ: Samsung" style="width:100%"><span id="customerCompanyFeedback" role="status" style="display:block;font-size:12px;margin-top:5px"></span></label>
   <label>Tên người đại diện *<input class="search" name="full_name" maxlength="255" required placeholder="Tên hiển thị" style="width:100%"></label>
   <label>Tên đăng nhập *<input class="search" name="username" minlength="3" maxlength="50" required pattern="[A-Za-z0-9_.-]+" placeholder="samsung_01" style="width:100%"></label>
   ${passwordField('password','Mật khẩu')}
   ${passwordField('confirm_password','Xác nhận mật khẩu')}
   <span id="customerPasswordFeedback" role="status" style="font-size:13px"></span>
 </form>`;
 const overlay=apModal('Tạo tài khoản khách hàng',html,async overlay=>{
  const form=overlay.querySelector('#newCustomerForm');
  if(!form.reportValidity())return false;
  const data=Object.fromEntries(new FormData(form).entries());
  const normalizedInput=String(data.company_name||'').trim().replace(/\s+/g,' ').toLocaleLowerCase('vi-VN');
  if(existingCompanyNames?.has(normalizedInput)){
    const feedback=overlay.querySelector('#customerCompanyFeedback');
    if(feedback){feedback.textContent='Công ty đã tồn tại. Vui lòng nhập tên công ty khác.';feedback.style.color='#b91c1c';}
    form.elements.company_name.setAttribute('aria-invalid','true');
    form.elements.company_name.focus();
    throw Error('Công ty đã tồn tại. Vui lòng nhập tên công ty khác.');
  }
  if(data.password!==data.confirm_password)throw Error('Hai mật khẩu không khớp. Vui lòng nhập lại.');
  let response;
  try{response=await fetch('/api/customer-orders/companies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
  catch(e){throw Error('Không thể kết nối tới server: '+e.message);}
  if(!response.ok){
    const raw=await response.text();let detail;
    try{detail=JSON.parse(raw);}catch{detail=raw;}
    if(response.status===409){
      const errorMessage=customerApiError(detail,response.status);
      const duplicateCompany=/tên công ty|công ty đã tồn tại/i.test(errorMessage);
      const badInput=duplicateCompany?form.elements.company_name:form.elements.username;
      badInput?.setAttribute('aria-invalid','true');
      if(duplicateCompany){
        const feedback=overlay.querySelector('#customerCompanyFeedback');
        if(feedback){
          feedback.textContent='Công ty đã tồn tại. Vui lòng nhập tên công ty khác.';
          feedback.style.color='#b91c1c';
        }
      }
      badInput?.focus();
    }
    throw Error(customerApiError(detail,response.status)+(response.status===405?' — Hãy tắt server cũ và khởi chạy app.py từ đúng thư mục vừa giải nén.':''));
  }
  const result=await response.json();
  await loadCustomers();
  alert(`Đã tạo tài khoản ${result.username} cho công ty ${data.company_name}.`);
  return true;
 },'Tạo tài khoản');
 overlay.querySelectorAll('.customer-password-eye').forEach(btn=>btn.addEventListener('click',()=>{
  const inp=overlay.querySelector(`[name="${btn.dataset.for}"]`);
  const show=inp.type==='password';inp.type=show?'text':'password';btn.textContent=show?'👁 Ẩn':'👁 Hiện';
  btn.setAttribute('aria-pressed',String(show));btn.setAttribute('aria-label',(show?'Ẩn ':'Hiện ')+(btn.dataset.for==='password'?'mật khẩu':'xác nhận mật khẩu'));
 }));
 const form=overlay.querySelector('#newCustomerForm');
 const saveButton=overlay.querySelector('.ap-modal-save');
 const modalError=overlay.querySelector('.ap-modal-error');
 const passwordFeedback=overlay.querySelector('#customerPasswordFeedback');
 const companyFeedback=overlay.querySelector('#customerCompanyFeedback');
 const normalizeCompany=name=>String(name||'').trim().replace(/\s+/g,' ').toLocaleLowerCase('vi-VN');
 let existingCompanyNames=null;
 let fetchingCompanies=true;
 fetch('/api/customer-orders/companies',{cache:'no-store'})
  .then(async response=>{if(!response.ok)throw Error('Không kiểm tra được tên công ty');return response.json();})
  .then(companies=>{existingCompanyNames=new Set(companies.map(c=>normalizeCompany(c.company_name)));})
  .catch(()=>{existingCompanyNames=null;}) // Server still enforces uniqueness.
  .finally(()=>{fetchingCompanies=false;refreshCustomerForm();});
 // Khi sửa một trường sau lỗi từ server, không giữ thông báo cũ hay khóa nút vô thời hạn.
 const refreshCustomerForm=()=>{
  const password=form.elements.password.value;
  const confirmation=form.elements.confirm_password.value;
  const matching=Boolean(confirmation) && password===confirmation;
  passwordFeedback.textContent=!confirmation?'':matching?'✓ Hai mật khẩu đã khớp':'Hai mật khẩu chưa khớp';
  passwordFeedback.style.color=matching?'#047857':'#b91c1c';
  const companyName=normalizeCompany(form.elements.company_name.value);
  const companyDuplicate=Boolean(companyName && existingCompanyNames?.has(companyName));
  companyFeedback.textContent=companyDuplicate?'Công ty đã tồn tại. Vui lòng nhập tên công ty khác.':'';
  companyFeedback.style.color='#b91c1c';
  form.elements.company_name.setAttribute('aria-invalid',String(companyDuplicate));
  saveButton.disabled=!form.checkValidity() || !matching || companyDuplicate || fetchingCompanies;
 };
 form.addEventListener('input',event=>{
  // Lỗi HTTP 409 (tên đăng nhập trùng) chỉ đúng với lần gửi trước.
  if(modalError)modalError.textContent='';
  if(event.target?.name==='username')event.target.removeAttribute('aria-invalid');
  refreshCustomerForm();
 });
 form.addEventListener('change',refreshCustomerForm);
 // Ngăn submit Enter gây tải lại trang, dùng chung luồng kiểm tra của nút lưu.
 form.addEventListener('submit',event=>{event.preventDefault();if(!saveButton.disabled)saveButton.click();});
 refreshCustomerForm();
}

function openDeleteCustomerAccount(company,account){
 if(window.currentUser?.role!=='admin')return;
 const content=`<div class="co-review-message"><span class="co-review-symbol" aria-hidden="true">?</span><p>Bạn có chắc muốn xóa tài khoản <strong>${safeText(account.username)}</strong> của công ty <strong>${safeText(company.company_name)}</strong> không?<br><small>Chỉ được xóa khi tất cả công đơn còn hiệu lực đã hoàn thành (hoặc chưa có công đơn). Tài khoản sẽ ngừng đăng nhập và xuất hiện trong lịch sử đã xóa; lịch sử công đơn được giữ lại.</small></p></div>`;
 const modal=apModal('Xác nhận xóa tài khoản khách hàng',content,async()=>{
  const r=await fetch(`/api/customer-orders/companies/${encodeURIComponent(company.id)}/accounts/${encodeURIComponent(account.id)}`,{method:'DELETE'});
  if(!r.ok){const error=await r.json().catch(()=>({}));throw Error(typeof error.detail==='string'?error.detail:`Không thể xóa tài khoản (${r.status})`);}
  await loadCustomers();
  return true;
 },'Xóa');
 modal.querySelector('.ap-modal')?.classList.add('co-review-modal','co-review-approve');
 return modal;
}

async function loadCustomers(){
 if(window.currentUser?.role!=='admin')return;
 const body=document.getElementById('customersRows');if(!body)return;
 try{
  const r=await fetch('/api/customer-orders/companies',{cache:'no-store'});
  if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(e.detail||`API lỗi ${r.status}`);}
  const companies=await r.json();
  const records=[];
  const deletedRecords=[];
  for(const company of companies){
   const accounts=Array.isArray(company.accounts)?company.accounts:[];
   for(const account of accounts){
    if(!account)continue;
    if(account.is_active===true)records.push({company,account});
    else if(account.is_active===false)deletedRecords.push({company,account});
   }
  }
  records.sort((a,b)=>String(a.company.company_name||'').localeCompare(String(b.company.company_name||''),'vi')||String(a.account.username||'').localeCompare(String(b.account.username||''),'vi'));
  body.replaceChildren();
  for(const {company:c,account} of records){
   const row=document.createElement('tr');
   const fields=[c.company_name,account.username,c.order_count,new Date(c.created_at).toLocaleDateString('vi-VN')];
   for(const value of fields){const td=document.createElement('td');td.textContent=value;row.appendChild(td);}
   const status=document.createElement('td');
   const state=document.createElement('span');state.className='customer-account-status is-active';
   state.textContent='Hoạt động';status.appendChild(state);row.appendChild(status);
   const action=document.createElement('td');
   const remove=document.createElement('button');remove.type='button';remove.className='work-small-btn customer-account-remove';remove.textContent='Xóa';
   remove.title=`Xóa quyền truy cập của ${account.username}`;
   remove.addEventListener('click',()=>openDeleteCustomerAccount(c,account));action.appendChild(remove);
   row.appendChild(action);
   const history=document.createElement('td');history.className='customer-account-history-cell';
   const btn=document.createElement('button');btn.type='button';btn.className='work-small-btn';btn.textContent='Xem lịch sử tạo đơn';btn.onclick=()=>loadCompanyHistory(c.id);history.appendChild(btn);
   row.appendChild(history);body.appendChild(row);
  }
  if(!records.length){body.innerHTML='<tr><td colspan="7">Không có tài khoản khách hàng đang hoạt động.</td></tr>';}
  const deletedBody=document.getElementById('deletedCustomersRows');
  if(deletedBody){
   deletedBody.replaceChildren();
   deletedRecords.sort((a,b)=>String(a.company.company_name||'').localeCompare(String(b.company.company_name||''),'vi')||String(a.account.username||'').localeCompare(String(b.account.username||''),'vi'));
   for(const {company:c,account} of deletedRecords){
    const row=document.createElement('tr');
    for(const value of [c.company_name,account.username,account.full_name||'—',c.order_count]){
     const td=document.createElement('td');td.textContent=value;row.appendChild(td);
    }
    const status=document.createElement('td');
    const badge=document.createElement('span');badge.className='customer-account-status is-deleted';badge.textContent='Đã xóa';status.appendChild(badge);row.appendChild(status);
    const history=document.createElement('td');
    const btn=document.createElement('button');btn.type='button';btn.className='work-small-btn';btn.textContent='Xem lịch sử tạo đơn';btn.onclick=()=>loadCompanyHistory(c.id);history.appendChild(btn);row.appendChild(history);
    deletedBody.appendChild(row);
   }
   if(!deletedRecords.length){deletedBody.innerHTML='<tr><td colspan="6">Chưa có tài khoản khách hàng đã xóa.</td></tr>';}
  }
  filterCustomerRows();
 }catch(e){body.textContent='Không tải được khách hàng: '+e.message;}
}

function filterCustomerRows() {
 const keyword=(document.getElementById('customerSearch')?.value||'').trim().toLocaleLowerCase('vi');
 const table=document.getElementById('customersRows');if(!table)return;
 let visible=0;
 for(const row of table.querySelectorAll('tr')) {
  if(row.cells.length!==7 || row.id==='customerSearchEmpty')continue;
  const match=!keyword || [row.cells[0]?.textContent,row.cells[1]?.textContent].join(' ').toLocaleLowerCase('vi').includes(keyword);
  row.hidden=!match;if(match)visible++;
 }
 let empty=document.getElementById('customerSearchEmpty');
 if(!empty){empty=document.createElement('tr');empty.id='customerSearchEmpty';empty.innerHTML='<td colspan="7" class="empty">Không tìm thấy khách hàng phù hợp.</td>';table.appendChild(empty);}
 empty.hidden=visible>0 || !keyword;
}

async function loadCompanyHistory(companyId){
 if(window.currentUser?.role!=='admin')return;
 const panel=document.getElementById('customerHistoryPanel');
 const body=document.getElementById('customerHistoryRows');
 if(!panel||!body)return;
 panel.style.display='';body.textContent='Đang tải lịch sử...';
 try{
  const r=await fetch('/api/customer-orders/companies/'+encodeURIComponent(companyId)+'/orders');
  if(!r.ok)throw Error(await r.text());
  const data=await r.json();
  document.getElementById('customerHistoryTitle').textContent='Lịch sử tạo công đơn · '+data.company.company_name;
  body.replaceChildren();
  for(const o of data.orders){
   const tr=document.createElement('tr');
   for(const value of ['CD-'+String(o.id).padStart(7,'0'),o.created_by_username,o.product_name,o.workshop_name,o.quantity,coDateTime(o.created_at),coStatus[o.status]||o.status,coTimeline(o)]){
    const cell=document.createElement('td');cell.textContent=value??'—';tr.appendChild(cell);
   }body.appendChild(tr);
  }
  if(!data.orders.length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=8;cell.textContent='Khách hàng chưa tạo công đơn';row.appendChild(cell);body.appendChild(row);}
  panel.scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(e){body.textContent='Không tải được lịch sử: '+e.message;}
}
