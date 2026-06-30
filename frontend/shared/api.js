/** 水文监测智慧运营平台 - 共享API层 */
/* 统一 fetch 封装：超时 + 认证头 + 错误处理 */

var API = '/api';

// Token 管理（优先使用 window._token 缓存，其次 localStorage）
function _authHdrs(){var h={};var t='';try{t=window._token||localStorage.getItem('water_ops_token')||''}catch(e){}if(t)h['Authorization']='Bearer '+t;return h}

// 登录状态管理（统一调用 showLogin）
function _handle401(){
  try{window._token='';localStorage.removeItem('water_ops_token')}catch(e){}
  if(typeof showLogin==='function')showLogin()
}

// GET 请求（带超时）
async function af(url,to){
  to=to||30000;
  try{
    var c=new AbortController();setTimeout(function(){c.abort()},to);
    var r=await fetch(API+url,{signal:c.signal,headers:_authHdrs()});
    if(r.status===401){_handle401();return null}
    var ct=(r.headers.get('content-type')||'').toLowerCase();
    if(ct.includes('application/json'))return await r.json();
    var txt=await r.text();return r.ok?[]:null
  }catch(e){console.error('af:',url,e);return null}
}

// POST 请求（带超时）
async function afP(url,d,to){
  to=to||30000;
  try{
    var c=new AbortController();setTimeout(function(){c.abort()},to);
    var r=await fetch(API+url,{method:'POST',headers:Object.assign({'Content-Type':'application/json'},_authHdrs()),body:JSON.stringify(d),signal:c.signal});
    if(r.status===401){_handle401();return{error:'auth'}}
    var ct=(r.headers.get('content-type')||'').toLowerCase();
    if(ct.includes('application/json'))return await r.json();
    var txt=await r.text();return{success:r.ok,error:r.ok?null:txt.substring(0,100)}
  }catch(e){console.error('afP:',url,e);return{error:String(e)}}
}

// PUT 请求（带超时）
async function afPt(url,d,to){
  to=to||30000;
  try{
    var c=new AbortController();setTimeout(function(){c.abort()},to);
    var r=await fetch(API+url,{method:'PUT',headers:Object.assign({'Content-Type':'application/json'},_authHdrs()),body:JSON.stringify(d),signal:c.signal});
    if(r.status===401){_handle401();return{error:'auth'}}
    var ct=(r.headers.get('content-type')||'').toLowerCase();
    if(ct.includes('application/json'))return await r.json();
    var txt=await r.text();return{success:r.ok,error:r.ok?null:txt.substring(0,100)}
  }catch(e){console.error('afPt:',url,e);return{error:String(e)}}
}

// DELETE 请求
async function afD(url,to){
  to=to||30000;
  try{
    var c=new AbortController();setTimeout(function(){c.abort()},to);
    var r=await fetch(API+url,{method:'DELETE',headers:_authHdrs(),signal:c.signal});
    if(r.status===401){_handle401();return{error:'auth'}}
    var ct=(r.headers.get('content-type')||'').toLowerCase();
    if(ct.includes('application/json'))return await r.json();
    var txt=await r.text();return{success:r.ok,error:r.ok?null:txt.substring(0,100)}
  }catch(e){console.error('afD:',url,e);return{error:String(e)}}
}
