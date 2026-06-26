var _recData=[];
async function ldEquipRecycle(){
  try{
    var kw=document.getElementById('rec-search').value.trim();
    var st=document.getElementById('rec-status').value;
    var url='/device-recycle?';
    if(kw) url+='search='+encodeURIComponent(kw)+'&';
    if(st) url+='status='+st;
    var rows=await af(url);_recData=rows||[];
    var stats=document.getElementById('rec-stats');
    if(stats) stats.innerHTML='<span style="color:#b0d4ef">回收记录 <b style="color:#00e0c0;font-family:monospace">'+_recData.length+'</b> 条</span>';
    _initPg('rec-body', _recData);
  }catch(e){}
}
window['_renderTable_rec-body']=function(rows){
  var h='';
  for(var i=0;i<rows.length;i++){
    var r=rows[i];
    var stMap={'recycled':'已回收','scrapped':'已报废','transferred':'已调拨'};
    var stClr=r.status==='recycled'?'#ffa040':r.status==='scrapped'?'#ff4760':'#2ea080';
    h+='<tr style="cursor:pointer" onclick="showRecycleDetail('+r.id+')">'
      +'<td style="font-family:monospace;font-size:11px">'+esc(r.device_code||'')+'</td>'
      +'<td>'+esc(r.device_name||'')+'</td>'
      +'<td style="font-size:11px;color:#5ea8c8">'+esc(r.site_name||'')+'</td>'
      +'<td style="font-size:11px">'+(r.recycle_date||'').substring(0,10)+'</td>'
      +'<td style="font-size:11px;color:#d0e8ff">'+esc(r.destination||'')+'</td>'
      +'<td style="font-size:11px;color:#5ea8c8" title="'+esc(r.reason||'')+'">'+esc((r.reason||'').substring(0,8))+'</td>'
      +'<td style="color:'+stClr+';font-size:11px">'+(stMap[r.status]||r.status)+'</td>'
      +'<td style="font-size:11px">'+esc(r.operator||'')+'</td>'
      +'<td><button class="btn btn-xs" style="color:#00e0c0;border:1px solid rgba(0,200,180,0.2)" onclick="event.stopPropagation();showRecycleDetail('+r.id+')">详情</button></td></tr>';
  }
  if(!h) h='<tr><td colspan="9" style="color:#5ea8c8;text-align:center;padding:20px">暂无回收记录</td></tr>';
  document.getElementById('rec-body').innerHTML=h;
};
function showRecycleDetail(recId){
  var r=_recData.find(function(x){return x.id===recId});if(!r)return;
  var stMap={'recycled':'已回收','scrapped':'已报废','transferred':'已调拨'};
  var stClr=r.status==='recycled'?'#ffa040':r.status==='scrapped'?'#ff4760':'#2ea080';
  var html='<div class="modal" style="max-width:500px"><h4>&#187;&#187;&#187; 设备回收详情</h4>'
    +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;color:#b0d4ef;background:rgba(0,0,0,0.15);padding:10px;border-radius:4px;margin-bottom:10px">'
    +'<div>设备编码：<b style="color:#d0e8ff;font-family:monospace">'+esc(r.device_code||'')+'</b></div>'
    +'<div>设备名称：<b style="color:#d0e8ff">'+esc(r.device_name||'')+'</b></div>'
    +'<div>设备类型：<b style="color:#5ea8c8">'+(DEVICE_TYPE_CN[r.device_type]||r.device_type||'')+'</b></div>'
    +'<div>原属站点：<b>'+esc(r.site_name||'')+'</b></div>'
    +'</div>'
    +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;color:#b0d4ef;padding:4px 0">'
    +'<div>回收日期：<b style="color:#d0e8ff">'+(r.recycle_date||'').substring(0,10)+'</b></div>'
    +'<div>回收状态：<b style="color:'+stClr+'">'+(stMap[r.status]||r.status)+'</b></div>'
    +'<div>设备去向：<b style="color:#00e0c0;font-size:13px">'+esc(r.destination||'')+'</b></div>'
    +'<div>经办人：<b>'+esc(r.operator||'')+'</b></div>'
    +'<div style="grid-column:1/3">回收原因：<b style="color:#d0e8ff">'+esc(r.reason||'')+'</b></div>'
    +'<div style="grid-column:1/3">备注：<b style="color:#5ea8c8">'+esc(r.remark||'')+'</b></div>'
    +'<div style="grid-column:1/3;color:#4a8aaa;font-size:11px">登记时间：'+(r.created_at||'')+'</div>'
    +'</div>'
    +'<div style="display:flex;gap:8px;margin-top:10px;justify-content:flex-end">'
    +'<button class="btn btn-sm" style="color:#ffa040;border:1px solid rgba(255,160,64,0.3)" onclick="event.stopPropagation();editRecycleDest('+r.id+',\''+esc(r.destination||'')+'\',\''+esc(r.remark||'')+'\');this.closest(\'.modal-overlay\').remove()">编辑去向</button>'
    +'<button class="btn btn-sm" style="color:#4a8aaa;border:1px solid rgba(0,200,180,0.15)" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button></div></div>';
  var ov=document.createElement('div');ov.className='modal-overlay';ov.innerHTML=html;document.body.appendChild(ov);
}
function showRecycleForm(devId,devCode,devName,siteName){
  var ov=document.createElement('div');ov.className='modal-overlay';
  var today=new Date().toISOString().substring(0,10);
  ov.innerHTML='<div class="modal" style="max-width:450px"><h4>&#187;&#187;&#187; 设备回收登记</h4>'
    +'<div style="margin-bottom:8px;font-size:12px;color:#5ea8c8">设备：<b style="color:#d0e8ff">'+devName+'</b> ('+devCode+') | 原站点：<b>'+siteName+'</b></div>'
    +'<div class="form-row"><label>回收日期</label><input type="date" id="rec-date" value="'+today+'"></div>'
    +'<div class="form-row"><label>回收状态</label><select id="rec-status-form"><option value="recycled">已回收</option><option value="scrapped">已报废</option><option value="transferred">已调拨</option></select></div>'
    +'<div class="form-row"><label>设备去向 *</label><input id="rec-dest" placeholder="如：退回仓库/报废处理/调拨至XX站"></div>'
    +'<div class="form-row"><label>回收原因</label><textarea id="rec-reason" rows="2" style="resize:vertical" placeholder="如：到寿更换/故障修复/设备升级"></textarea></div>'
    +'<div class="form-row"><label>经办人</label><input id="rec-operator" placeholder="填写经办人姓名" value="'+(_user?._user?.real_name||'')+'"></div>'
    +'<div class="form-row"><label>备注</label><input id="rec-remark" placeholder="其他说明（可选）"></div>'
    +'<div style="display:flex;gap:8px;margin-top:8px"><button class="btn btn-primary" onclick="submitRecycle('+devId+')">确认回收</button>'
    +'<button class="btn" style="color:#4a8aaa;border:1px solid rgba(0,200,180,0.15)" onclick="this.closest(\'.modal-overlay\').remove()">取消</button></div></div>';
  document.body.appendChild(ov);
}
async function submitRecycle(devId){
  var date=document.getElementById('rec-date').value;
  var status=document.getElementById('rec-status-form').value;
  var dest=document.getElementById('rec-dest').value.trim();
  var reason=document.getElementById('rec-reason').value.trim();
  var operator=document.getElementById('rec-operator').value.trim();
  var remark=document.getElementById('rec-remark').value.trim();
  if(!dest){alert('请填写设备去向');return}
  var r=await afP('/device-recycle',{
    device_id:devId, recycle_date:date, status:status,
    destination:dest, reason:reason, operator:operator, remark:remark
  });
  if(r&&r.success){
    alert('回收登记成功');document.querySelectorAll('.modal-overlay').forEach(function(e){e.remove()});
    ldEquipLedger();ldEquipRecycle();
  }else{alert(r&&r.error||'登记失败')}
}
function editRecycleDest(recId,dest,remark){
  var nd=prompt('更新设备去向：',dest);if(nd===null)return;
  var nr=prompt('更新备注：',remark);if(nr===null)return;
  afPt('/device-recycle/'+recId,{destination:nd,remark:nr}).then(function(r){
    if(r&&r.success) ldEquipRecycle();
    else alert('更新失败');
  });
}

// ===== 通知系统 =====

var _notifPanelOpen=false;
function toggleNotifPanel(){
  var p=document.getElementById('notif-panel');
  if(!p||_notifPanelOpen){ closeNotifPanel(); return }
  _notifPanelOpen=true;
  p.style.display='block';
  loadNotifList();
}
function closeNotifPanel(){
  _notifPanelOpen=false;
  var p=document.getElementById('notif-panel');
  if(p)p.style.display='none';
}
async function loadNotifList(){
  var list=document.getElementById('notif-list');
  if(!list)return;
  list.innerHTML='<div style="text-align:center;padding:12px;color:#5ea8c8;font-size:11px">鍔犺浇涓?..</div>';
  try{
    var d=await af('/notifications?limit=30');
    if(!d||!d.notifications){list.innerHTML='<div style="text-align:center;padding:12px;color:#5ea8c8;font-size:11px">鏆傛棤閫氱煡</div>';return}
    var h='';
    for(var i=0;i<d.notifications.length;i++){
      var n=d.notifications[i];
      var bg=n.is_read?'':'background:rgba(0,200,180,0.03)';
      var dot=n.is_read?'':'<span style="display:inline-block;width:6px;height:6px;background:#00e0c0;border-radius:50%;margin-right:4px"></span>';
      h+='<div class="notif-item" style="display:flex;align-items:flex-start;gap:6px;padding:8px 10px;border-bottom:1px solid rgba(0,200,180,0.04);'+bg+';cursor:pointer" onclick="'+(n.is_read?'':'markNotifRead('+n.id+')')+'">'
        +'<div style="flex:1;min-width:0">'
        +'<div style="font-size:12px;color:#d0e8ff;display:flex;align-items:center">'+dot+(n.title||'')+'</div>'
        +'<div style="font-size:10px;color:#5ea8c8;margin-top:2px">'+(n.content||'')+'</div>'
        +'<div style="font-size:9px;color:#4a8aaa;margin-top:2px">'+(n.created_at||'').substring(0,16)+'</div></div></div>';
    }
    if(!h)h='<div style="text-align:center;padding:12px;color:#5ea8c8;font-size:11px">鏆傛棤閫氱煡</div>';
    list.innerHTML=h;
    updateNotifBadge(d.unread_count);
  }catch(e){list.innerHTML='<div style="text-align:center;padding:12px;color:#5ea8c8;font-size:11px">鍔犺浇澶辫触</div>'}
}
async function updateNotifBadge(count){
  var badge=document.getElementById('notif-badge');
  if(!badge)return;
  if(count>0){badge.style.display='block';badge.textContent=count>99?'99+':count}
  else badge.style.display='none';
  // 涔熸洿鏂板鑸粺璁?
  var ns=document.getElementById('ns-alerts');
  if(ns){
    var txt=ns.textContent;
    if(count>0&&txt.indexOf('馃敂')<0)ns.textContent='馃敂'+count+' | '+txt;
    else if(count===0)ns.textContent=txt.replace(/馃敂\d+\s*\|\s*/,'');
  }
}
async function markNotifRead(nid){
  await afPt('/notifications/'+nid+'/read',{});
  loadNotifList();
}
async function markAllNotifRead(){
  await afPt('/notifications/read-all',{});
  loadNotifList();
}
// 瀹氭湡杞鏈閫氱煡
setInterval(async function(){
  try{
    var d=await af('/notifications/unread-count');
    if(d&&typeof d.count==='number')updateNotifBadge(d.count);
  }catch(e){}
},15000);  // 姣?5绉掓鏌?
// 宸ュ崟鍒楄〃瀹氭椂鍒锋柊锛堢‘淇濈Щ鍔ㄧ涓婃姤鐨勫伐鍗曞疄鏃舵樉绀猴級
setInterval(async function(){
  try{await ldOr()}catch(e){}
},15000);  // 姣?5绉掑埛鏂板伐鍗曞垪琛?

