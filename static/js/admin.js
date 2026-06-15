// ShiftGuard — Admin Dashboard

let allEmployees=[], allBranches=[], gBranch='', resetPinId=null;

document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.nav-link').forEach(l=>
    l.addEventListener('click',e=>{e.preventDefault();switchTab(e.currentTarget.dataset.tab);}));
  const today=new Date().toISOString().split('T')[0];
  const month=today.substring(0,7);
  sv('att-from',new Date(Date.now()-30*864e5).toISOString().split('T')[0]);
  sv('att-to',today);sv('rpt-date',today);sv('rpt-month',month);
  sv('sal-month',month);sv('att-add-date',today);
  sv('ph-from',new Date(Date.now()-7*864e5).toISOString().split('T')[0]);sv('ph-to',today);
  loadAll();
});

async function loadAll(){await loadBranches();loadDashboard();loadEmployees();loadBlocked();loadAdmins();}

function sv(id,v){const e=document.getElementById(id);if(e)e.value=v;}
function gv(id){const e=document.getElementById(id);return e?e.value:'';}
function msg(type,text){
  ['ok','err','info'].forEach(t=>{const e=document.getElementById('msg-'+t);if(e)e.classList.remove('show');});
  const el=document.getElementById('msg-'+type);if(!el)return;
  el.textContent=text;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),5000);
}
async function api(url,method,body){
  method=method||'GET';
  const opts={method,headers:{'Content-Type':'application/json'}};
  if(body)opts.body=JSON.stringify(body);
  const r=await fetch(url,opts);return r.json();
}
function fmtT(ts){if(!ts)return'—';try{return new Date(ts).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'});}catch{return(ts+'').substring(11,16)||'—';}}
function fmtDT(ts){if(!ts)return'';try{return new Date(ts).toISOString().substring(0,16);}catch{return(ts+'').substring(0,16);}}
function badge(s){var m={on_time:'b-green',completed:'b-green',late:'b-yellow',early_departure:'b-yellow',pending:'b-blue',absent:'b-red'};return'<span class="badge '+(m[s]||'b-gray')+'">'+(s||'—')+'</span>';}
function thumb(url,id,field){
  if(!url)return'<span class="no-photo">—</span>';
  return'<img class="photo-thumb" src="'+url+'" onclick="showLightbox(\''+url+'\')" alt="photo"><button class="btn btn-danger btn-xs" style="margin-left:.2rem" onclick="delPhoto('+id+',\''+field+'\')">🗑</button>';
}
function showLightbox(src){document.getElementById('lb-img').src=src;document.getElementById('lightbox').classList.add('open');}
function setBranch(v){gBranch=v;loadDashboard();loadEmployees();}
function openM(id){var m=document.getElementById(id);if(m)m.classList.add('open');}
function closeM(id){var m=document.getElementById(id);if(m)m.classList.remove('open');}
window.addEventListener('click',function(e){if(e.target.classList.contains('modal'))e.target.classList.remove('open');});

function switchTab(name){
  document.querySelectorAll('.tab-content').forEach(function(t){t.classList.remove('active');});
  document.querySelectorAll('.nav-link').forEach(function(l){l.classList.remove('active');});
  var t=document.getElementById(name);if(t)t.classList.add('active');
  var l=document.querySelector('[data-tab="'+name+'"]');if(l)l.classList.add('active');
  if(name==='attendance')loadAttendance();
  if(name==='employees')loadEmployees();
  if(name==='branches')loadBranches();
  if(name==='salary')populateSalEmpSel();
  if(name==='security'){loadBlocked();loadNetworkInfo();}
  if(name==='settings')loadAdmins();
  if(name==='photos')loadPhotos();
}

async function loadDashboard(){
  var d=await api('/api/admin/dashboard'+(gBranch?'?branch_id='+gBranch:''));
  document.getElementById('s-total').textContent=d.total_employees||0;
  document.getElementById('s-in').textContent=d.checked_in||0;
  document.getElementById('s-out').textContent=d.checked_out||0;
  document.getElementById('s-late').textContent=d.late||0;
  document.getElementById('s-absent').textContent=d.absent||0;
  document.getElementById('today-date').textContent=d.today||'';
  var tb=document.getElementById('today-tbody');
  if(!(d.logs||[]).length){tb.innerHTML='<tr><td colspan="9" style="text-align:center;padding:2rem;color:#78909c">No check-ins yet today</td></tr>';return;}
  tb.innerHTML=(d.logs||[]).map(function(l){return'<tr><td><strong>'+l.name+'</strong><br><small style="color:#78909c">'+l.position+'</small></td><td>'+(l.branch_name||'—')+'</td><td>'+(l.check_in?fmtT(l.check_in):'—')+'</td><td>'+thumb(l.check_in_photo,l.id,'check_in_photo')+'</td><td>'+(l.check_out?fmtT(l.check_out):'—')+'</td><td>'+thumb(l.check_out_photo,l.id,'check_out_photo')+'</td><td>'+(l.hours_worked||0)+'h</td><td>'+(l.minutes_late>0?'<span style="color:var(--warning)">'+l.minutes_late+'m</span>':'—')+'</td><td>'+badge(l.status)+'</td></tr>';}).join('');
}

async function loadAttendance(){
  var url='/api/admin/attendance?start='+gv('att-from')+'&end='+gv('att-to')+(gBranch?'&branch_id='+gBranch:'');
  var d=await api(url);
  var tb=document.getElementById('att-tbody');
  if(!(d.logs||[]).length){tb.innerHTML='<tr><td colspan="11" style="text-align:center;padding:2rem;color:#78909c">No records found</td></tr>';return;}
  tb.innerHTML=(d.logs||[]).map(function(l){return'<tr><td><strong>'+l.name+'</strong></td><td>'+(l.branch_name||'—')+'</td><td>'+l.date+'</td><td>'+fmtT(l.check_in)+'</td><td>'+thumb(l.check_in_photo,l.id,'check_in_photo')+'</td><td>'+fmtT(l.check_out)+'</td><td>'+thumb(l.check_out_photo,l.id,'check_out_photo')+'</td><td>'+(l.hours_worked||0)+'h</td><td>'+(l.minutes_late>0?'<span style="color:var(--warning)">'+l.minutes_late+'m</span>':'—')+'</td><td>'+badge(l.status)+'</td><td><button class="btn btn-warn btn-xs" onclick="openEditAtt('+l.id+',\''+l.check_in+'\',\''+l.check_out+'\',\''+l.notes+'\')">✏️</button></td></tr>';}).join('');
}

function openEditAtt(id,ci,co,notes){sv('att-edit-id',id);sv('att-ci',fmtDT(ci));sv('att-co',fmtDT(co));sv('att-notes',notes||'');openM('att-modal');}
async function saveAttEdit(){
  var id=gv('att-edit-id');
  var d=await api('/api/admin/attendance/'+id,'PUT',{check_in:gv('att-ci')||null,check_out:gv('att-co')||null,notes:gv('att-notes')});
  if(d.success){msg('ok','Record updated');closeM('att-modal');loadAttendance();}else msg('err',d.message);
}
async function deleteAtt(){
  if(!confirm('Delete this attendance record? Cannot be undone.'))return;
  var id=gv('att-edit-id');
  var d=await api('/api/admin/attendance/'+id,'DELETE');
  if(d.success){msg('ok','Deleted');closeM('att-modal');loadAttendance();}
}
function openAddAtt(){
  populateEmpSel('att-add-emp');
  sv('att-add-date',new Date().toISOString().split('T')[0]);
  sv('att-add-ci','');sv('att-add-co','');sv('att-add-notes','');
  openM('att-add-modal');
}
async function saveManualAtt(){
  var d=await api('/api/admin/attendance/add','POST',{employee_id:parseInt(gv('att-add-emp')),date:gv('att-add-date'),check_in:gv('att-add-ci')||null,check_out:gv('att-add-co')||null,notes:gv('att-add-notes')});
  if(d.success){msg('ok','Record added');closeM('att-add-modal');loadAttendance();}else msg('err','Failed');
}
async function delPhoto(id,field){
  if(!confirm('Delete this photo permanently?'))return;
  var d=await api('/api/admin/attendance/'+id+'/delete-photo','POST',{field:field});
  if(d.success){msg('ok','Photo deleted');loadDashboard();loadAttendance();}
}

async function loadEmployees(){
  var d=await api('/api/admin/employees'+(gBranch?'?branch_id='+gBranch:''));
  allEmployees=d.employees||[];
  var tb=document.getElementById('emp-tbody');
  if(!allEmployees.length){tb.innerHTML='<tr><td colspan="8" style="text-align:center;padding:2rem;color:#78909c">No employees yet.</td></tr>';return;}
  tb.innerHTML=allEmployees.map(function(e){return'<tr><td><strong>'+e.name+'</strong></td><td>'+(e.position||'—')+'</td><td>'+(e.branch_name||'—')+'</td><td>'+(e.phone||'—')+'</td><td>'+e.shift_start+'–'+e.shift_end+'</td><td style="font-size:.78rem">'+(e.working_days||'').replace(/,/g,' ')+'</td><td>'+(e.salary_amount?'$'+parseFloat(e.salary_amount).toLocaleString():'—')+'</td><td style="display:flex;gap:.3rem;flex-wrap:wrap"><button class="btn btn-warn btn-xs" onclick="editEmp('+e.id+')">✏️ Edit</button><button class="btn btn-primary btn-xs" onclick="openResetPin('+e.id+',\''+e.name+'\')">🔑 PIN</button><button class="btn btn-danger btn-xs" onclick="delEmp('+e.id+',\''+e.name+'\')">🗑 Delete</button></td></tr>';}).join('');
}

function openAddEmp(){
  document.getElementById('emp-modal-title').textContent='➕ Add Employee';
  document.getElementById('emp-id').value='';
  ['e-name','e-pin','e-pos','e-phone','e-sal','e-hire'].forEach(function(id){sv(id,'');});
  sv('e-ss','09:30');sv('e-se','18:30');sv('e-saltype','monthly');
  document.querySelectorAll('#wd-grid input').forEach(function(c){c.checked=c.value!=='Sun';});
  populateBranchSel('e-branch');openM('emp-modal');
}
function editEmp(id){
  var e=allEmployees.find(function(x){return x.id===id;});if(!e)return;
  document.getElementById('emp-modal-title').textContent='✏️ Edit Employee';
  sv('emp-id',e.id);sv('e-name',e.name);sv('e-pin','');sv('e-pos',e.position||'');sv('e-phone',e.phone||'');
  sv('e-ss',e.shift_start);sv('e-se',e.shift_end);sv('e-saltype',e.salary_type||'monthly');sv('e-sal',e.salary_amount||'');sv('e-hire',e.hire_date||'');
  var wd=(e.working_days||'Mon,Tue,Wed,Thu,Fri,Sat').split(',');
  document.querySelectorAll('#wd-grid input').forEach(function(c){c.checked=wd.includes(c.value);});
  populateBranchSel('e-branch',e.branch_id);openM('emp-modal');
}
async function saveEmp(){
  var id=gv('emp-id');var name=gv('e-name').trim();var pin=gv('e-pin').trim();
  if(!name)return msg('err','Name is required');
  if(!id&&!pin)return msg('err','PIN required for new employees');
  if(pin&&(pin.length!==4||!/^\d+$/.test(pin)))return msg('err','PIN must be 4 digits');
  var wd=Array.from(document.querySelectorAll('#wd-grid input:checked')).map(function(c){return c.value;}).join(',');
  var payload={name:name,position:gv('e-pos'),phone:gv('e-phone'),branch_id:parseInt(gv('e-branch'))||1,shift_start:gv('e-ss'),shift_end:gv('e-se'),working_days:wd,salary_type:gv('e-saltype'),salary_amount:parseFloat(gv('e-sal'))||0,hire_date:gv('e-hire')||null};
  if(pin)payload.pin=pin;
  var d=await api(id?'/api/admin/employees/'+id:'/api/admin/employees',id?'PUT':'POST',payload);
  if(d.success){msg('ok',d.message);closeM('emp-modal');loadEmployees();}else msg('err',d.message);
}
async function delEmp(id,name){
  if(!confirm('⚠️ PERMANENTLY delete "'+name+'"?\n\nThis removes ALL their attendance records and salary history.\n\nThis CANNOT be undone.'))return;
  var d=await api('/api/admin/employees/'+id,'DELETE');
  if(d.success){msg('ok',name+' permanently deleted');loadEmployees();loadDashboard();}else msg('err',d.message);
}
function openResetPin(id,name){
  resetPinId=id;document.getElementById('pin-name').textContent='Employee: '+name;sv('new-pin','');openM('pin-modal');
}
async function doResetPin(){
  var pin=gv('new-pin').trim();
  if(pin.length!==4||!/^\d+$/.test(pin))return msg('err','PIN must be 4 digits');
  var d=await api('/api/admin/employees/'+resetPinId+'/reset-pin','POST',{pin:pin});
  if(d.success){msg('ok',d.message);closeM('pin-modal');}else msg('err',d.message);
}

async function loadBranches(){
  var d=await api('/api/admin/branches');allBranches=d.branches||[];
  var tb=document.getElementById('branch-tbody');
  if(tb)tb.innerHTML=allBranches.map(function(b){return'<tr><td><strong>'+b.name+'</strong></td><td>'+(b.address||'—')+'</td><td>'+(b.phone||'—')+'</td><td><span class="badge '+(b.is_active?'b-green':'b-red')+'">'+(b.is_active?'Active':'Inactive')+'</span></td><td><button class="btn btn-warn btn-xs" onclick="editBranch('+b.id+')">✏️</button> <button class="btn btn-danger btn-xs" onclick="delBranch('+b.id+',\''+b.name+'\')">🗑</button></td></tr>';}).join('');
  return allBranches;
}
function populateBranchSel(selId,selectedId){
  var s=document.getElementById(selId);if(!s)return;
  s.innerHTML=allBranches.filter(function(b){return b.is_active;}).map(function(b){return'<option value="'+b.id+'"'+(b.id==selectedId?' selected':'')+'>'+b.name+'</option>';}).join('');
}
function populateEmpSel(selId){
  var s=document.getElementById(selId);if(!s)return;
  s.innerHTML=allEmployees.map(function(e){return'<option value="'+e.id+'">'+e.name+' ('+(e.branch_name||'?')+')</option>';}).join('');
}
function openAddBranch(){document.getElementById('branch-modal-title').textContent='🏢 Add Branch';sv('br-id','');['br-name','br-addr','br-phone'].forEach(function(id){sv(id,'');});openM('branch-modal');}
function editBranch(id){var b=allBranches.find(function(x){return x.id===id;});if(!b)return;document.getElementById('branch-modal-title').textContent='✏️ Edit Branch';sv('br-id',b.id);sv('br-name',b.name);sv('br-addr',b.address||'');sv('br-phone',b.phone||'');openM('branch-modal');}
async function saveBranch(){
  var id=gv('br-id');var name=gv('br-name').trim();if(!name)return msg('err','Branch name required');
  var d=await api(id?'/api/admin/branches/'+id:'/api/admin/branches',id?'PUT':'POST',{name:name,address:gv('br-addr'),phone:gv('br-phone')});
  if(d.success){msg('ok',d.message||'Saved');closeM('branch-modal');await loadBranches();}else msg('err',d.message);
}
async function delBranch(id,name){if(!confirm('Delete branch "'+name+'"?'))return;await api('/api/admin/branches/'+id,'DELETE');msg('ok','Removed');loadBranches();}

async function populateSalEmpSel(){
  var d=await api('/api/admin/employees');
  var s=document.getElementById('sal-emp');
  s.innerHTML='<option value="">— All Employees —</option>'+(d.employees||[]).map(function(e){return'<option value="'+e.id+'">'+e.name+'</option>';}).join('');
}
async function calcSalary(){
  var mv=gv('sal-month');if(!mv)return msg('err','Select a month');
  var parts=mv.split('-');var year=parseInt(parts[0]);var month=parseInt(parts[1]);
  var eid=gv('sal-emp');msg('info','Calculating...');
  var d=await api('/api/admin/salary/calculate','POST',{year:year,month:month,employee_id:eid||null});
  if(!d.success)return msg('err','Failed');
  msg('ok','Calculated '+d.records.length+' record(s)');
  document.getElementById('sal-results').innerHTML=(d.records||[]).map(function(r){return'<div class="sal-card"><h4 style="color:var(--dark);margin-bottom:.8rem">👤 '+r.employee_name+' — '+r.year+'/'+String(r.month).padStart(2,'0')+'</h4><div class="sal-row"><span>Base Salary</span><span>$'+r.base_salary.toLocaleString()+'</span></div><div class="sal-row"><span>Days Present / Scheduled</span><span>'+r.days_present+' / '+r.working_days+'</span></div><div class="sal-row"><span>Absent Deduction</span><span class="ded">−$'+r.absent_deduction.toFixed(2)+'</span></div><div class="sal-row"><span>Late Deduction ('+r.total_late_min+' min)</span><span class="ded">−$'+r.late_deduction.toFixed(2)+'</span></div><div class="sal-row"><span>Overtime Pay ('+r.overtime_hours+'h)</span><span class="add">+$'+r.overtime_pay.toFixed(2)+'</span></div><div class="sal-row"><span>NET SALARY</span><span>$'+r.net_salary.toLocaleString()+'</span></div></div>';}).join('');
}
async function loadSalHistory(){
  var yr=gv('sal-yr');var mo=gv('sal-mo');
  var url='/api/admin/salary/records?';if(yr)url+='year='+yr+'&';if(mo)url+='month='+mo;
  var d=await api(url);var tb=document.getElementById('sal-hist-tbody');
  if(!(d.records||[]).length){tb.innerHTML='<tr><td colspan="10" style="text-align:center;color:#78909c;padding:1.5rem">No records</td></tr>';return;}
  tb.innerHTML=(d.records||[]).map(function(r){return'<tr><td><strong>'+r.name+'</strong></td><td>'+r.year+'/'+String(r.month).padStart(2,'0')+'</td><td>$'+(r.base_salary||0).toLocaleString()+'</td><td style="color:var(--success)">'+r.days_present+'</td><td style="color:var(--danger)">'+r.days_absent+'</td><td style="color:var(--warning)">'+r.days_late+'</td><td>+'+(r.overtime_hours||0).toFixed(2)+'h</td><td style="color:var(--danger)">−$'+((r.absent_deduction||0)+(r.late_deduction||0)).toFixed(2)+'</td><td><strong style="color:var(--primary)">$'+(r.net_salary||0).toLocaleString()+'</strong></td><td>'+(r.is_paid?'<span class="badge b-green">✅ Paid</span>':'<button class="btn btn-success btn-xs" onclick="markPaid('+r.employee_id+','+r.year+','+r.month+')">Mark Paid</button>')+'</td></tr>';}).join('');
}
async function markPaid(eid,yr,mo){var d=await api('/api/admin/salary/mark-paid','POST',{employee_id:eid,year:yr,month:mo});if(d.success){msg('ok','Marked as paid');loadSalHistory();}}

function dlReport(type){
  var url;
  if(type==='daily'){var dt=gv('rpt-date');if(!dt)return msg('err','Select a date');url='/api/admin/report/daily?date='+dt;}
  else{var mo=gv('rpt-month');if(!mo)return msg('err','Select a month');url='/api/admin/report/monthly?month='+mo;}
  if(gBranch)url+='&branch_id='+gBranch;
  msg('info','Generating...');window.open(url,'_blank');
}

async function loadPhotos(){
  var d=await api('/api/admin/photos?start='+gv('ph-from')+'&end='+gv('ph-to'));
  var grid=document.getElementById('photo-grid');var photos=d.photos||[];
  if(!photos.length){grid.innerHTML='<p style="color:#78909c;grid-column:1/-1">No photos in this date range.</p>';return;}
  grid.innerHTML=photos.map(function(p){return'<div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.1);border:1px solid #c8e8e8"><img src="'+p.url+'" style="width:100%;height:120px;object-fit:cover;cursor:pointer" onclick="showLightbox(\''+p.url+'\')" alt=""><div style="padding:.5rem .6rem"><div style="font-size:.8rem;font-weight:600">'+p.employee+'</div><div style="font-size:.72rem;color:#78909c">'+p.date+' · '+p.type+'</div><button class="btn btn-danger btn-xs" style="margin-top:.4rem;width:100%" onclick="delPhoto('+p.att_id+',\''+p.field+'\');this.closest(\'div\').parentElement.remove()">🗑 Delete</button></div></div>';}).join('');
}

async function loadBlocked(){
  var d=await api('/api/admin/blocked-sites');var tb=document.getElementById('blocked-tbody');
  tb.innerHTML=(d.sites||[]).map(function(s){return'<tr><td><code style="color:var(--primary)">'+s.domain+'</code></td><td>'+s.category+'</td><td><button class="btn btn-danger btn-xs" onclick="delBlocked('+s.id+')">Remove</button></td></tr>';}).join('')||'<tr><td colspan="3" style="text-align:center;color:#78909c;padding:1rem">No blocked sites</td></tr>';
}
async function addBlocked(){
  var domain=gv('new-domain').trim().toLowerCase();if(!domain)return msg('err','Enter a domain');
  var d=await api('/api/admin/blocked-sites','POST',{domain:domain,category:gv('new-cat')});
  if(d.success){msg('ok','Added to block list');sv('new-domain','');loadBlocked();}else msg('err',d.message);
}
async function delBlocked(id){
  if(!confirm('Remove this site?'))return;
  await api('/api/admin/blocked-sites/'+id,'DELETE');msg('ok','Removed');loadBlocked();
}

async function loadNetworkInfo(){
  try{
    var d=await api('/api/admin/network/info');
    var info=d.info||{};var hs=d.hosts_status||{};
    var sip=info.server_ip||'—';var gw=info.gateway||'—';
    document.getElementById('n-ip').textContent=sip;
    document.getElementById('n-gw').textContent=gw;
    var hostsEl=document.getElementById('n-hosts');
    hostsEl.textContent=hs.active?'🔒 Active ('+hs.count+' domains)':'🔓 Not Active';
    hostsEl.style.color=hs.active?'var(--success)':'var(--danger)';
    var rl=document.getElementById('router-link');if(rl&&gw!=='—'){rl.textContent='http://'+gw;}
    var di=document.getElementById('dns-ip');if(di)di.textContent=sip;
  }catch(e){console.error(e);}
}
async function scanNetwork(){
  msg('info','Scanning network... please wait');
  try{
    var d=await api('/api/admin/network/scan');var devices=d.devices||[];
    document.getElementById('n-devcount').textContent=devices.length;
    var tb=document.getElementById('devices-tbody');
    if(!devices.length){tb.innerHTML='<tr><td colspan="4" style="text-align:center;padding:1.5rem;color:#78909c">No devices found</td></tr>';return;}
    tb.innerHTML=devices.map(function(dv){return'<tr><td><code style="color:var(--primary)">'+dv.ip+'</code></td><td><code style="font-size:.78rem">'+dv.mac+'</code></td><td>'+(dv.hostname||'<span style="color:#78909c">Unknown</span>')+'</td><td><span class="badge b-blue">'+dv.type+'</span></td></tr>';}).join('');
    msg('ok','Found '+devices.length+' device(s)');
  }catch(e){msg('err','Scan failed');}
}
async function applyHosts(){
  if(!confirm('Apply blocking on THIS computer?\nRequires running as Administrator.\n\nContinue?'))return;
  msg('info','Applying blocks...');
  var d=await api('/api/admin/network/apply-hosts','POST');
  if(d.success){msg('ok',d.message);loadNetworkInfo();}else msg('err',d.message);
}
async function removeHosts(){
  if(!confirm('Remove ALL blocks from this computer?'))return;
  var d=await api('/api/admin/network/remove-hosts','POST');
  if(d.success){msg('ok',d.message);loadNetworkInfo();}else msg('err',d.message);
}

async function loadLogs(){
  var d=await api('/api/admin/logs');var tb=document.getElementById('logs-tbody');
  tb.innerHTML=(d.logs||[]).map(function(l){return'<tr><td style="font-size:.78rem">'+(l.created_at||'').substring(0,16)+'</td><td><span class="badge '+(l.event_type.includes('fail')?'b-red':'b-blue')+'">'+l.event_type+'</span></td><td>'+(l.user||'—')+'</td><td style="font-size:.78rem">'+(l.ip||'—')+'</td><td style="font-size:.78rem">'+(l.details||'—')+'</td></tr>';}).join('')||'<tr><td colspan="5" style="text-align:center;color:#78909c;padding:1rem">No logs</td></tr>';
}

function applyPreset(p,s){document.getElementById('th-p').value='#'+p;sv('th-p-hex',p);document.getElementById('th-s').value='#'+s;sv('th-s-hex',s);}
async function saveTheme(){
  var payload={primary:gv('th-p-hex')||document.getElementById('th-p').value.replace('#',''),secondary:gv('th-s-hex')||document.getElementById('th-s').value.replace('#',''),font:gv('th-font'),logo_text:gv('th-name')||'ShiftGuard',dark_mode:gv('th-dark')};
  var d=await api('/api/admin/theme','POST',payload);
  if(d.success){msg('ok','Theme saved! Refreshing...');setTimeout(function(){location.reload();},1200);}else msg('err',d.message);
}
async function changePw(){
  var cur=gv('pw-cur'),nw=gv('pw-new'),cfm=gv('pw-cfm');
  if(!cur||!nw||!cfm)return msg('err','All fields required');
  if(nw!==cfm)return msg('err','Passwords do not match');
  if(nw.length<8)return msg('err','Minimum 8 characters');
  var d=await api('/api/admin/change-password','POST',{current_password:cur,new_password:nw});
  if(d.success){msg('ok',d.message);setTimeout(function(){location.href='/admin/login';},2000);}else msg('err',d.message);
}
async function loadAdmins(){
  var d=await api('/api/admin/users');var tb=document.getElementById('admin-tbody');if(!tb)return;
  tb.innerHTML=(d.users||[]).map(function(u){return'<tr><td><strong>'+u.username+'</strong></td><td>'+u.role+'</td><td>'+(u.branch_id?u.branch_id:'All')+'</td><td style="font-size:.78rem">'+(u.last_login?(u.last_login+'').substring(0,16):'Never')+'</td><td><span class="badge '+(u.is_active?'b-green':'b-red')+'">'+(u.is_active?'Active':'Inactive')+'</span></td></tr>';}).join('');
}
function openAddAdmin(){
  sv('adm-u','');sv('adm-pw','');sv('adm-role','admin');
  var s=document.getElementById('adm-branch');
  s.innerHTML='<option value="">All Branches</option>'+allBranches.filter(function(b){return b.is_active;}).map(function(b){return'<option value="'+b.id+'">'+b.name+'</option>';}).join('');
  openM('admin-modal');
}
async function saveAdmin(){
  var d=await api('/api/admin/users','POST',{username:gv('adm-u').trim(),password:gv('adm-pw'),role:gv('adm-role'),branch_id:gv('adm-branch')||null});
  if(d.success){msg('ok','Admin created');closeM('admin-modal');loadAdmins();}else msg('err',d.message);
}
async function doLogout(){
  if(!confirm('Logout?'))return;
  await api('/admin/logout','POST');location.href='/admin/login';
}
