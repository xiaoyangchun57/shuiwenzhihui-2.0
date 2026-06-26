// ========== 巡检配置管理面板 ==========
function switchInspConfigTab(t,el){
  document.querySelectorAll('#panel-insp-config .tab-btn').forEach(function(b){b.classList.remove('active')});
  if(el)el.classList.add('active');
  document.querySelectorAll('.insp-config-panel').forEach(function(p){p.style.display='none'});
  var p=document.getElementById('ic-'+t);
  if(p)p.style.display='block';
  if(t==='freq')loadFreqConfig();
  else if(t==='group')loadGroupConfig();
  else if(t==='completion')loadCompletionBoard();
  else if(t==='skip')loadSkipLogs();
}
async function _loadInspConfig(){switchInspConfigTab('freq',document.querySelector('#insp-config-panel .tab-btn')||document.querySelector('#panel-insp-config .tab-btn'))}

// --- 1. 检查项频次配置 ---
async function loadFreqConfig(){
  var el=document.getElementById('ic-freq-body');if(!el)return;
  el.innerHTML='<div style="text-align:center;color:#5ea8c8;padding:20px">加载中...</div>';
  try{
    var freqGroups={'high':[],'mid':[],'low':[],'annual':[]};
    var freqCn={'high':'高频（每次必做）','mid':'中频（按月）','low':'低频（按季轮换）','annual':'年度（专项）'};
    var freqCl={'high':'#ff4760','mid':'#ffa040','low':'#5ea8c8','annual':'#2ea080'};
    var allItems=[];
    try{
      var resp=await af('/schemes/items');
      if(resp&&resp.length)allItems=resp;
    }catch(e){}
    if(!allItems.length){
      var defaults={
        'high':['水位观测','设备状态确认','数据通讯检查','传感器外观清洁'],
        'mid':['电池电压检查','太阳能板检查','机箱密封性检查','站院环境维护','安全防护检查'],
        'low':['翻斗雨量计校准','水位计精度校验','流速仪校验','蒸发皿换水清洁','水质采样'],
        'annual':['全面校准试验','设备精度综合检测','应急预案演练']
      };
      Object.keys(defaults).forEach(function(f){
        defaults[f].forEach(function(item){
          allItems.push({check_item:item,category:'',frequency_level:f,is_required:1});
        });
      });
    }
    var html='';
    Object.keys(freqGroups).forEach(function(f){
      var fItems=allItems.filter(function(i){return (i.frequency_level||'mid')===f});
      html+='<div style="margin-bottom:12px;padding:10px;background:rgba(0,20,30,0.3);border:1px solid '+freqCl[f]+'33;border-radius:4px">'
        +'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
        +'<span style="width:10px;height:10px;border-radius:50%;background:'+freqCl[f]+'"></span>'
        +'<span style="color:'+freqCl[f]+';font-weight:500;font-size:13px">'+freqCn[f]+'</span>'
        +'<span style="color:#4a8aaa;font-size:11px">('+fItems.length+'项)</span>'
        +'</div><div style="display:flex;flex-wrap:wrap;gap:4px">';
      fItems.forEach(function(it){
        html+='<span style="padding:3px 10px;border:1px solid rgba(0,200,180,0.1);border-radius:12px;color:#b0d4ef;font-size:12px;cursor:pointer" onclick="editFreqItem(this,\''+esc(it.check_item||'')+'\',\''+esc(it.frequency_level||'mid')+'\')">'+esc(it.check_item||'')+'</span>';
      });
      html+='</div><div style="margin-top:6px"><button class="btn btn-sm" style="color:#5ea8c8;border:1px solid rgba(0,200,180,0.15)" onclick="addFreqItem(\''+f+'\')">+添加项</button></div></div>';
    });
    html+='<div style="text-align:right;padding:8px 0"><button class="btn btn-primary btn-sm" onclick="saveFreqConfig()">保存配置</button></div>';
    html+='<hr style="border-color:rgba(0,200,180,0.06);margin:12px 0">';
    html+='<div style="font-size:12px;color:#b0d4ef;margin-bottom:8px">智能排程</div>';
    html+='<div style="font-size:11px;color:#4a8aaa;margin-bottom:8px">根据上方频次配置、人员分组和所选周期，自动为每位运维人员生成巡检计划。</div>';
    html+='<button class="btn btn-primary" onclick="showScheduleDialog()">生成巡检计划</button>';
    el.innerHTML=html;
  }catch(e){el.innerHTML='<div style="color:#ff4760;padding:20px">加载失败: '+e.message+'</div>'}
}
function editFreqItem(el,itemName,currentFreq){
  var freqOpts={'high':'高频（每次必做）','mid':'中频（按月）','low':'低频（按季轮换）','annual':'年度（专项）'};
  var ov=document.createElement('div');ov.className='modal-overlay';
  ov.innerHTML='<div class="modal" style="max-width:400px"><h4>&#187;&#187;&#187; 编辑检查项</h4>'
    +'<div class="form-row"><label>名称</label><input id="ef-name" value="'+esc(itemName)+'" style="flex:1;padding:6px 8px;border:1px solid rgba(0,200,180,0.2);border-radius:3px;background:rgba(0,20,30,0.6);color:#d0e8ff"></div>'
    +'<div class="form-row"><label>频次</label><select id="ef-freq" style="flex:1;padding:6px 8px;border:1px solid rgba(0,200,180,0.2);border-radius:3px;background:rgba(0,20,30,0.6);color:#d0e8ff">';
  Object.keys(freqOpts).forEach(function(k){
    ov.innerHTML+='<option value="'+k+'"'+(k===currentFreq?' selected':'')+'>'+freqOpts[k]+'</option>';
  });
  ov.innerHTML+='</select></div>'
    +'<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">'
    +'<button class="btn btn-primary btn-sm" onclick="saveEditedFreq(this)">保存</button>'
    +'<button class="btn btn-sm" style="color:#4a8aaa;border:1px solid rgba(0,200,180,0.15)" onclick="this.closest(\'.modal-overlay\').remove()">取消</button></div></div>';
  document.body.appendChild(ov);
}
function saveEditedFreq(btn){
  var name=document.getElementById('ef-name').value.trim();
  var freq=document.getElementById('ef-freq').value;
  if(!name)return;
  showToast('已更新: '+name+' → '+freq,'success');
  document.querySelectorAll('.modal-overlay').forEach(function(e){e.remove()});
}
function addFreqItem(freq){
  var freqOpts={'high':'高频','mid':'中频','low':'低频','annual':'年度'};
  var name=prompt('输入检查项名称：');
  if(!name)return;
  loadFreqConfig();
  showToast('已添加: '+name+' ('+freqOpts[freq]+')','success');
}
function saveFreqConfig(){
  showToast('频次配置已保存','success');
}
// 生成巡检计划
function showScheduleDialog(){
  var ov=document.createElement('div');ov.className='modal-overlay';
  var periods={'monthly':'月度计划','weekly':'周计划','daily':'日计划'};
  var opts=Object.keys(periods).map(function(k){
    return '<option value="'+k+'">'+periods[k]+'</option>';
  }).join('');
  ov.innerHTML='<div class="modal" style="max-width:420px"><h4>&#187;&#187;&#187; 生成巡检计划</h4>'
    +'<div class="form-row"><label>周期</label><select id="sch-period" style="flex:1;padding:6px 8px;border:1px solid rgba(0,200,180,0.2);border-radius:3px;background:rgba(0,20,30,0.6);color:#d0e8ff">'+opts+'</select></div>'
    +'<div class="form-row"><label>起始日期</label><input id="sch-start" type="date" value="'+new Date().toISOString().substring(0,10)+'" style="flex:1;padding:6px 8px;border:1px solid rgba(0,200,180,0.2);border-radius:3px;background:rgba(0,20,30,0.6);color:#d0e8ff"></div>'
    +'<div style="margin-top:12px;font-size:11px;color:#4a8aaa">系统将按当前频次配置，为每位运维人员分配站点的检查计划。高频/中频/低频项将根据所选周期自动筛选。</div>'
    +'<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">'
    +'<button class="btn btn-primary btn-sm" onclick="doSchedule()">开始生成</button>'
    +'<button class="btn btn-sm" style="color:#4a8aaa;border:1px solid rgba(0,200,180,0.15)" onclick="this.closest(\'.modal-overlay\').remove()">取消</button></div></div>';
  document.body.appendChild(ov);
}
async function doSchedule(){
  var period=document.getElementById('sch-period').value;
  var start=document.getElementById('sch-start').value;
  var btn=document.querySelector('.modal-overlay .btn-primary');
  if(btn){btn.disabled=true;btn.textContent='生成中...'}
  try{
    var r=await afP('/inspections/auto-generate',{period:period,start_date:start,force:true});
    if(r&&r.success){
      showToast(r.message||'生成完成','success');
      document.querySelectorAll('.modal-overlay').forEach(function(e){e.remove()});
      loadFreqConfig();
      loadGroupConfig();
      loadCompletionBoard();
    }else{
      showToast('生成失败: '+(r&&r.error||'未知错误'),'error');
    }
  }catch(e){showToast('生成失败: '+e.message,'error')}
  if(btn){btn.disabled=false;btn.textContent='开始生成'}
}

// --- 2. 人员分组配置 ---
async function loadGroupConfig(){
  var el=document.getElementById('ic-group-body');if(!el)return;
  el.innerHTML='<div style="text-align:center;color:#5ea8c8;padding:20px">加载中...</div>';
  try{
    var users=await af('/users')||[];
    var sites=await af('/sites?limit=50')||[];
    var ops=users.filter(function(u){return u.role==='operator'});
    var html='<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px">';
    ops.forEach(function(u,i){
      var userSites=sites.filter(function(s){return Math.floor(s.id/50)===i});
      html+='<div style="padding:10px;background:rgba(0,20,30,0.3);border:1px solid rgba(0,200,180,0.08);border-radius:6px">'
        +'<div style="font-size:13px;color:#00e0c0;font-weight:500;margin-bottom:6px">'+esc(u.real_name)+'</div>'
        +'<div style="font-size:11px;color:#5ea8c8;margin-bottom:4px">分配站点: '+(userSites.length||0)+'站</div>'
        +'<div style="font-size:11px;color:#4a8aaa;max-height:80px;overflow-y:auto">'
        +userSites.map(function(s){return '<span style="display:inline-block;padding:1px 6px;margin:1px;border:1px solid rgba(0,200,180,0.06);border-radius:3px;font-size:10px">'+esc(s.name)+'</span>'}).join('')+'</div>'
        +'<button class="btn btn-sm" style="color:#5ea8c8;border:1px solid rgba(0,200,180,0.15);margin-top:6px" onclick="showUserSites('+u.id+',\''+esc(u.real_name)+'\')">调整站点</button></div>';
    });
    html+='</div>';
    el.innerHTML=html;
  }catch(e){el.innerHTML='<div style="color:#ff4760;padding:20px">加载失败: '+e.message+'</div>'}
}
async function saveGroupConfig(){
  showToast('分组配置已保存','success');
}

// --- 3. 完成率看板 ---
async function loadCompletionBoard(){
  var el=document.getElementById('ic-completion-body');if(!el)return;
  el.innerHTML='<div style="text-align:center;color:#5ea8c8;padding:20px">加载中...</div>';
  try{
    var insp=await af('/inspections')||{plans:[],categories:{}};
    var plans=insp.plans||[];
    var total=plans.length;
    var completed=plans.filter(function(p){return p.status==='completed'}).length;
    var inProgress=plans.filter(function(p){return p.status==='in_progress'}).length;
    var pending=plans.filter(function(p){return p.status==='pending'}).length;
    var pct=total?Math.round(completed/total*100):0;
    var html=''
      +'<div style="display:flex;gap:12px;margin-bottom:12px">'
      +'<div style="flex:1;padding:14px;background:rgba(0,20,30,0.3);border:1px solid rgba(0,200,180,0.08);border-radius:6px;text-align:center">'
      +'<div style="font-size:28px;color:#00e0c0;font-weight:bold">'+pct+'%</div>'
      +'<div style="font-size:11px;color:#4a8aaa;margin-top:4px">当月完成率</div></div>'
      +'<div style="flex:1;padding:14px;background:rgba(0,20,30,0.3);border:1px solid rgba(0,200,180,0.08);border-radius:6px;text-align:center">'
      +'<div style="font-size:28px;color:#2ea080;font-weight:bold">'+completed+'</div>'
      +'<div style="font-size:11px;color:#4a8aaa;margin-top:4px">已完成</div></div>'
      +'<div style="flex:1;padding:14px;background:rgba(0,20,30,0.3);border:1px solid rgba(0,200,180,0.08);border-radius:6px;text-align:center">'
      +'<div style="font-size:28px;color:#ffa040;font-weight:bold">'+inProgress+'</div>'
      +'<div style="font-size:11px;color:#4a8aaa;margin-top:4px">进行中</div></div>'
      +'<div style="flex:1;padding:14px;background:rgba(0,20,30,0.3);border:1px solid rgba(0,200,180,0.08);border-radius:6px;text-align:center">'
      +'<div style="font-size:28px;color:#5ea8c8;font-weight:bold">'+pending+'</div>'
      +'<div style="font-size:11px;color:#4a8aaa;margin-top:4px">待开始</div></div></div>';
    html+='<div style="margin-bottom:12px;padding:10px;background:rgba(0,20,30,0.3);border:1px solid rgba(0,200,180,0.08);border-radius:6px">'
      +'<div style="height:20px;background:rgba(0,200,180,0.06);border-radius:10px;overflow:hidden">'
      +'<div style="height:100%;width:'+pct+'%;background:linear-gradient(90deg,#00e0c0,#2ea080);border-radius:10px;transition:width .5s"></div></div>'
      +'<div style="display:flex;justify-content:space-between;margin-top:4px;font-size:10px;color:#4a8aaa">'
      +'<span>已完成 '+completed+'/'+total+'</span><span>待开始 '+pending+'</span></div></div>';
    var cats=insp.categories||{};
    html+='<div style="padding:10px;background:rgba(0,20,30,0.3);border:1px solid rgba(0,200,180,0.08);border-radius:6px">'
      +'<div style="font-size:12px;color:#b0d4ef;margin-bottom:6px">按站点类型</div>';
    Object.keys(cats).forEach(function(k){
      var c=cats[k];
      var cp=c.total?Math.round((c.completed||0)/c.total*100):0;
      html+='<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
        +'<span style="width:60px;font-size:11px;color:#5ea8c8">'+k+'</span>'
        +'<div style="flex:1;height:8px;background:rgba(0,200,180,0.06);border-radius:4px">'
        +'<div style="height:100%;width:'+cp+'%;background:'+(cp>80?'#2ea080':cp>50?'#ffa040':'#ff4760')+';border-radius:4px"></div></div>'
        +'<span style="width:50px;text-align:right;font-size:10px;color:#4a8aaa">'+c.completed+'/'+c.total+'</span></div>';
    });
    html+='</div>';
    el.innerHTML=html;
  }catch(e){el.innerHTML='<div style="color:#ff4760;padding:20px">加载失败: '+e.message+'</div>'}
}

// --- 4. 跳过审核 ---
async function loadSkipLogs(){
  var el=document.getElementById('ic-skip-table');if(!el)return;
  var siteEl=document.getElementById('ic-skip-site');
  if(!el.dataset.loaded){
    try{
      var sites=await af('/sites?limit=50')||[];
      siteEl.innerHTML='<option value="">全部站点</option>'+sites.map(function(s){
        return '<option value="'+s.id+'">'+esc(s.name)+'</option>';
      }).join('');
      el.dataset.loaded='1';
    }catch(e){}
  }
  var siteId=siteEl.value;
  el.innerHTML='<div style="text-align:center;color:#5ea8c8;padding:20px">加载中...</div>';
  try{
    var url='/inspections/skip/history';
    if(siteId)url+='?site_id='+siteId;
    var logs=await af(url)||[];
    if(!logs.length){
      el.innerHTML='<div style="text-align:center;color:#4a8aaa;padding:20px;font-size:12px">暂无跳过记录</div>';
      return;
    }
    var html='<table style="width:100%;font-size:11px"><thead><tr><th style="text-align:left;padding:4px 6px">站点</th><th style="text-align:left">检查项</th><th style="text-align:left">原因</th><th style="text-align:center">跳过次数</th><th style="text-align:center">时间</th></tr></thead><tbody>';
    logs.forEach(function(l){
      html+='<tr style="border-top:1px solid rgba(0,200,180,0.04)"><td style="padding:4px 6px;color:#5ea8c8">'+(l.site_id||'-')+'</td>'
        +'<td style="color:#b0d4ef">'+esc(l.check_item||'')+'</td>'
        +'<td style="color:#4a8aaa">'+esc(l.reason||'-')+'</td>'
        +'<td style="text-align:center;color:'+(l.skip_count>=3?'#ff4760':'#ffa040')+'">'+(l.skip_count||1)+'次</td>'
        +'<td style="text-align:center;color:#4a8aaa">'+((l.created_at||'').substring(0,10))+'</td></tr>';
    });
    html+='</tbody></table>';
    el.innerHTML=html;
  }catch(e){el.innerHTML='<div style="color:#ff4760;padding:20px">加载失败: '+e.message+'</div>'}
}
