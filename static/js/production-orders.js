/* Production Order Admin UI. Shared Dashboard helpers remain in app.js. */
// ===== Quản lý Production Order (Admin) =====
function poUpdateAdminUI() {
    const b=document.getElementById('poCreateBtn');
    if(b) b.style.display=['admin','customer'].includes(window.currentUser?.role)?'inline-flex':'none';
    const f=document.getElementById('poWorkshopFilter');
    if(f){ const old=f.value;const groups=[...new Set(dashboardPOs.map(p=>p.workshop_name).filter(Boolean))].sort();
      f.innerHTML='<option value="">Tất cả xưởng</option>'+groups.map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');f.value=old; }
}
async function poOpenCreate(){
    if(window.currentUser?.role==='customer')return customerOpenCreateModal();
    if(window.currentUser?.role!=='admin')return alert('Chỉ Admin hoặc khách hàng được tạo công đơn');
    let data;
    try{data=await apRequest('/api/production-orders/options');}catch(e){return alert(e.message+' — Hãy chạy migration 003 trước.');}
    const today=new Date().toLocaleDateString('en-CA');
 const dateValue=value=>value?String(value).slice(0,10):today;
    const opts=(list,id,label)=>list.map(x=>`<option value="${x[id]}">${esc(x[label])}</option>`).join('');
    const body=`<div class="po-form-grid">
      <label>Mã công đơn<input value="Hệ thống cấp mã khi tạo thành công" disabled></label>
      <label>Xưởng *<select name="workshop_id">${opts(data.workshops,'id','workshop_name')}</select></label>
      <label>Sản phẩm *<select name="product_id">${data.products.map(x=>`<option value="${x.id}">${esc(x.product_code)} — ${esc(x.product_name)}</option>`).join('')}</select></label>
      <label>Số lượng kế hoạch *<input type="number" name="planned_quantity" min="1" required value="1000"></label>
      <label>Bắt đầu kế hoạch *<input type="date" name="planned_start" value="${dateValue(existing?.planned_start)}" required></label>
      <label>Kết thúc kế hoạch *<input type="date" name="planned_end" value="${dateValue(existing?.expected_date)}" required></label>
      <label>Trạng thái ban đầu<select name="status"><option value="Planned">Kế hoạch</option><option value="In Progress">Đang sản xuất</option></select></label>
      <fieldset class="po-machine-picker"><legend>Máy thực hiện (chọn ít nhất một) *</legend><div id="poMachines"></div></fieldset>
      <p class="po-form-hint">PO mới sẽ liên kết với xưởng, sản phẩm và các máy đã chọn. Chưa có sản lượng thực tế cho đến khi ghi nhận sản xuất.</p>
    </div>`;
    const modal=apModal('Tạo công đơn',body,async(el)=>{
       const val=(n)=>el.querySelector(`[name="${n}"]`)?.value;
       const machines=[...el.querySelectorAll('input[name="po_machine"]:checked')].map(x=>Number(x.value));
       if(!machines.length)throw Error('Chọn ít nhất một máy');
       const body={workshop_id:+val('workshop_id'),product_id:+val('product_id'),
         planned_quantity:+val('planned_quantity'),planned_start:val('planned_start'),planned_end:val('planned_end'),
         status:val('status'),machine_ids:machines};
       const created=await apRequest('/api/production-orders','POST',body);await loadDashboard();alert('Đã tạo công đơn: '+created.order_code);return true;
    },'Tạo công đơn');
    function updateMachines(){const wid=+modal.querySelector('[name="workshop_id"]').value;
      modal.querySelector('#poMachines').innerHTML=data.machines.filter(x=>x.workshop_id===wid).map(x=>
        `<label><input type="checkbox" name="po_machine" value="${x.id}"> ${esc(x.machine_code)} — ${esc(x.machine_name)}</label>`).join('')||'<p>Chưa có máy trong xưởng này</p>';}
    modal.querySelector('[name="workshop_id"]').addEventListener('change',updateMachines);updateMachines();
}
async function poOpenAssignMachines(code, returnToEdit = false) {
    if (window.currentUser?.role !== 'admin') return;
    try {
        const [options, details] = await Promise.all([
            apRequest('/api/production-orders/options'),
            apRequest('/api/production-orders/' + encodeURIComponent(code) + '/record-details')
        ]);
        if(details.order.status === 'Completed') throw Error('PO đã hoàn thành, không thể thay đổi máy.');
        const workshop = options.workshops.find(w => w.workshop_code === details.order.workshop_code);
        if (!workshop) throw Error('Không tìm thấy xưởng của PO');
        const assigned = new Set((details.machines || []).map(m => Number(m.id)));
        const choices = options.machines.filter(m => Number(m.workshop_id) === Number(workshop.id));
        if(!choices.length) throw Error('Xưởng này chưa có máy để phân công');
        const overlay = apModal('Phân công máy · ' + code,
            `<p class="po-form-hint">Chỉ hiển thị máy thuộc ${esc(details.order.workshop_name)}. Máy đã có nhật ký sản xuất không thể bỏ khỏi PO.</p>
            <div class="po-machine-picker po-assignment-list">${choices.map(m => `<label><input type="checkbox" name="machine_id" value="${Number(m.id)}" ${assigned.has(Number(m.id))?'checked':''}> ${esc(m.machine_code)} — ${esc(m.machine_name)}</label>`).join('')}</div>`,
            async (el) => {
                const machine_ids = [...el.querySelectorAll('input[name="machine_id"]:checked')].map(input => Number(input.value));
                if(!machine_ids.length) throw Error('Chọn ít nhất một máy');
                await apRequest('/api/production-orders/' + encodeURIComponent(code) + '/machines', 'PUT', {machine_ids});
                await loadDashboard();
                if (returnToEdit) setTimeout(() => poOpenRecordDetails(code), 0);
                return true;
            }, 'Lưu phân công');
        return overlay;
    } catch(err) { alert(err.message || 'Không tải được máy của PO'); }
}
async function poAddRecord(code){
  if(window.currentUser?.role!=='admin')return;
  let options;try{options=await apRequest('/api/production-orders/options');}catch(e){return alert(e.message);}
  const po=dashboardPOs.find(x=>x.order_code===code);
  const machines=options.machines.filter(x=>(po?.machines||[]).some(m=>m.machine_code===x.machine_code));
  if(!machines.length)return alert('PO chưa có máy được phân công');
  const today=new Date().toLocaleDateString('en-CA');
  apModal(`Ghi nhận sản lượng · ${code}`,`<div class="po-form-grid">
    <label>Máy<select name="machine_id">${machines.map(m=>`<option value="${m.id}">${esc(m.machine_code)} — ${esc(m.machine_name)}</option>`).join('')}</select></label>
    <label>Ngày sản xuất<input type="date" name="production_date" value="${today}"></label>
    <label>Ca<input name="shift" value="Ca 1"></label>
    <label>Sản lượng<input type="number" name="quantity_produced" min="0" value="0"></label>
    <label>Số lượng lỗi<input type="number" name="quantity_defective" min="0" value="0"></label>
    <label>Phút sản xuất<input type="number" name="production_minutes" min="0" max="1440" value="420"></label>
  </div>`,async(el)=>{
    const v=n=>el.querySelector(`[name="${n}"]`).value;
    await apRequest(`/api/production-orders/${encodeURIComponent(code)}/records`,'POST',{
      machine_id:+v('machine_id'),production_date:v('production_date'),shift:v('shift'),quantity_produced:+v('quantity_produced'),quantity_defective:+v('quantity_defective'),production_minutes:+v('production_minutes')});
    await loadDashboard();return true;},'Lưu sản lượng');
}
async function poComplete(code){
  if(window.currentUser?.role!=='admin')return;
  if(!confirm(`XÁC NHẬN ĐÓNG PO ${code} đang sản xuất?\n\nPO chỉ được đóng khi công đoạn cuối đã đạt đủ sản lượng kế hoạch. Sau khi đóng sẽ không thể chỉnh sửa sản lượng.`))return;
  try{await apRequest(`/api/production-orders/${encodeURIComponent(code)}/complete`,'POST');await loadDashboard();}
  catch(e){alert(e.message);}
}


async function poCancel(code){
  if(window.currentUser?.role!=='admin')return;
  if(!confirm(`HỦY PO ${code} đang ở trạng thái Kế hoạch?\n\nPO sẽ chuyển thành Đã hủy, vẫn được giữ trong PostgreSQL và không thể ghi sản lượng mới. Thao tác này không phải xóa dữ liệu.`))return;
  try{await apRequest(`/api/production-orders/${encodeURIComponent(code)}/cancel`,'POST');await loadDashboard();}
  catch(e){alert(e.message);}
}

async function poStart(code) {
  if (window.currentUser?.role !== 'admin') return;
  if (!confirm(`Bắt đầu sản xuất PO ${code}?\nPO phải được phân công máy trước khi bắt đầu.`)) return;
  try {
    await apRequest(`/api/production-orders/${encodeURIComponent(code)}/start`, 'POST');
    await loadDashboard();
  } catch(e) { alert(e.message || 'Không thể bắt đầu sản xuất'); }
}

// ===== Sổ sản lượng chi tiết theo PO / máy =====
async function poOpenRecordDetails(code){
  if(window.currentUser?.role!=='admin')return;
  let data;
  try{data=await apRequest('/api/production-orders/'+encodeURIComponent(code)+'/record-details');}
  catch(e){alert(e.message);return;}
  const o=data.order||{}, machines=data.machines||[], records=data.records||[];
  const locked=o.status==='Completed'||o.status==='Cancelled';
  const fmtQty=n=>Number(n||0).toLocaleString('vi-VN');
  const dateText=v=>v?String(v).slice(0,10).split('-').reverse().join('/'):'—';
  const planned=Number(o.planned_quantity||0);
  // Sản lượng cuối dây chuyền: công đoạn cuối có process_order lớn nhất.
  // Không cộng tất cả máy vì một sản phẩm đi qua nhiều công đoạn.
  const processGroups=new Map();
  machines.forEach(m=>{
    const k=m.process_order==null?'unknown:'+m.id:String(m.process_order);
    const production=records.filter(r=>r.machine_id===m.id).reduce((sum,r)=>sum+Number(r.quantity_produced||0),0);
    if(!processGroups.has(k))processGroups.set(k,{order:m.process_order==null?-1:Number(m.process_order),quantity:0});
    processGroups.get(k).quantity+=production;
  });
  const lastProcess=Array.from(processGroups.values()).sort((a,b)=>b.order-a.order)[0];
  const actual=lastProcess?lastProcess.quantity:0;
  const completion=String(o.status||'').toLowerCase()==='completed'?100:(planned?Math.min(100,Math.max(0,actual/planned*100)):0);
  const outputRate=planned?Math.min(100,Math.max(0,actual/planned*100)):0;
  const shortage=Math.max(0,planned-actual);
  const allDefects=records.reduce((sum,r)=>sum+Number(r.quantity_defective||0),0);
  const metrics=`<section class="po-completion-summary">
     <div class="po-completion-title">Dữ liệu hoàn thành kế hoạch và sản lượng</div>
     <div class="po-completion-grid">
       <div><span>Tiến độ công việc</span><strong>${completion.toFixed(2)}%</strong></div>
       <div><span>Sản lượng kế hoạch</span><strong>${fmtQty(planned)}</strong></div>
       <div><span>Sản lượng thực tế (công đoạn cuối)</span><strong>${fmtQty(actual)}</strong></div>
       <div><span>Tỷ lệ đạt sản lượng</span><strong>${outputRate.toFixed(2)}%</strong></div>
       <div><span>Thiếu so với kế hoạch</span><strong>${fmtQty(shortage)}</strong></div>
       <div><span>Lỗi qua các công đoạn</span><strong>${fmtQty(allDefects)}</strong></div>
     </div>
     <div class="po-completion-track"><span style="width:${completion}%"></span></div>
   </section>`;
  const total=machines.map(m=>{
    const rs=records.filter(r=>r.machine_id===m.id);
    return {...m,rows:rs,produced:rs.reduce((a,r)=>a+Number(r.quantity_produced||0),0),
      defective:rs.reduce((a,r)=>a+Number(r.quantity_defective||0),0)};
  });
  const body=`<div class="po-detail-intro">
     <div><span>Mã PO</span><strong>${esc(o.order_code||code)}</strong></div>
     <div><span>Xưởng</span><strong>${esc(o.workshop_code||'—')}</strong></div>
     <div><span>Sản phẩm</span><strong>${esc(o.product_code||'—')}</strong></div>
     <div><span>Kế hoạch</span><strong>${fmtQty(o.planned_quantity)}</strong></div>
     <div><span>Trạng thái</span><strong>${locked?'Hoàn thành':esc(o.status||'—')}</strong></div>
    </div>
    ${metrics}
    ${!locked?`<div class="po-edit-toolbar"><strong>${String(o.status||'').trim().toLowerCase()==='planned'?'Sẵn sàng sản xuất':'Máy sản xuất'}</strong><div class="po-edit-toolbar-actions"><button type="button" class="po-edit-assign" data-po-manage-machines>Phân công máy</button>${String(o.status||'').trim().toLowerCase()==='planned'?`<button type="button" class="po-edit-assign po-start-action" data-po-start>▶ Bắt đầu sản xuất</button>`:''}</div></div>`:''}
    ${locked?'<p class="po-detail-locked">PO đã hoàn thành: chỉ xem, không sửa lịch sử.</p>':''}
    <div class="po-detail-machine-list">${total.map(m=>`<section class="po-detail-machine">
       <div class="po-detail-machine-head"><div><b>${esc(m.machine_code)} — ${esc(m.machine_name)}</b><small>${esc(m.process_name||'Công đoạn chưa xác định')} · ${m.rows.length} bản ghi</small></div>
       <div class="po-detail-totals"><span>Sản xuất: <strong>${fmtQty(m.produced)}</strong></span><span>Lỗi: <strong>${fmtQty(m.defective)}</strong></span></div></div>
       <div class="po-detail-table-wrap"><table class="po-detail-table"><thead><tr><th>Ngày sản xuất</th><th>Ca</th><th>Sản lượng</th><th>Lỗi</th><th>Phút SX</th><th>Thao tác</th></tr></thead><tbody>
       ${m.rows.length?m.rows.map(r=>`<tr><td>${dateText(r.production_date)}</td><td>${esc(r.shift)}</td><td>${fmtQty(r.quantity_produced)}</td><td>${fmtQty(r.quantity_defective)}</td><td>${fmtQty(r.production_minutes)}</td><td>${locked?'Đã khóa':`<button type="button" data-po-edit-id="${r.id}">Chỉnh sửa</button>`}</td></tr>`).join(''):`<tr><td colspan="6" class="po-detail-empty">Chưa có dữ liệu sản lượng ở máy này.</td></tr>`}</tbody></table></div>
     </section>`).join('')||'<p>PO chưa được gán máy. Hãy kiểm tra danh sách phân công máy.</p>'}</div>`;
  const overlay=apModal('Chỉnh sửa · '+code,body,null);
  overlay.querySelector('.ap-modal')?.classList.add('po-detail-modal');
  overlay.querySelector('[data-po-start]')?.addEventListener('click', async () => {
    if (!machines.length) {
      alert('PO chưa phân công máy. Vui lòng chọn máy trước khi bắt đầu.');
      overlay.remove();
      poOpenAssignMachines(code, true);
      return;
    }
    overlay.remove();
    await poStart(code);
  });
  overlay.querySelector('[data-po-manage-machines]')?.addEventListener('click', () => {
    overlay.remove();
    poOpenAssignMachines(code, true);
  });
  overlay.querySelectorAll('[data-po-edit-id]').forEach(btn=>btn.addEventListener('click',()=>{
    const rec=records.find(r=>r.id===Number(btn.dataset.poEditId));
    const machine=machines.find(m=>m.id===rec?.machine_id);
    overlay.remove();poEditRecord(code,machine,rec);
  }));
}
function poEditRecord(code,machine,rec){
  if(!machine)return alert('Không tìm thấy máy được phân công');
  const isEdit=!!rec;
  const today=new Date().toLocaleDateString('en-CA');
  const form=`<p class="po-detail-note">${esc(machine.machine_code)} — ${esc(machine.machine_name)}. ${isEdit?'Chỉnh sửa bản ghi hiện có; không tạo thêm dòng mới.':'Thêm nhật ký sản xuất cho máy này.'}</p>
  <div class="po-form-grid">
    <label>Ngày sản xuất *<input type="date" name="production_date" value="${esc(rec?.production_date||today)}" required></label>
    <label>Ca *<input name="shift" value="${esc(rec?.shift||'Ca 1')}" maxlength="50" required></label>
    <label>Sản lượng sản xuất *<input type="number" name="quantity_produced" min="0" step="1" value="${Number(rec?.quantity_produced??0)}" required></label>
    <label>Số lượng lỗi *<input type="number" name="quantity_defective" min="0" step="1" value="${Number(rec?.quantity_defective??0)}" required></label>
    <label>Phút sản xuất *<input type="number" name="production_minutes" min="0" max="1440" step="1" value="${Number(rec?.production_minutes??0)}" required></label>
  </div>`;
  const modal=apModal(`${isEdit?'Chỉnh sửa':'Ghi nhận'} sản lượng · ${machine.machine_code}`,form,async(el)=>{
    const val=name=>el.querySelector('[name="'+name+'"]')?.value;
    const body={machine_id:machine.id,production_date:val('production_date'),shift:val('shift')?.trim(),
      quantity_produced:Number(val('quantity_produced')),quantity_defective:Number(val('quantity_defective')),
      production_minutes:Number(val('production_minutes'))};
    if(!body.production_date||!body.shift||Object.values(body).some(v=>typeof v==='number'&&(!Number.isInteger(v)||v<0)))
      throw Error('Kiểm tra lại ngày, ca và các giá trị số nguyên không âm');
    if(body.quantity_defective>body.quantity_produced)throw Error('Số lượng lỗi không được lớn hơn sản lượng');
    const path='/api/production-orders/'+encodeURIComponent(code)+'/records'+(isEdit?'/'+rec.id:'');
    await apRequest(path,isEdit?'PATCH':'POST',body);
    await loadDashboard();
    await poOpenRecordDetails(code);
    return true;
  },isEdit?'Lưu thay đổi':'Thêm bản ghi');
  const close=modal.querySelector('.ap-modal-footer .ap-modal-close');
  if(close){close.textContent='Đóng';close.addEventListener('click',()=>poOpenRecordDetails(code));}
}
