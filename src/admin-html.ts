export const ADMIN_HTML = String.raw`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Miku OTP — Admin</title>
<style>
  :root { --teal:#0d9488; --ink:#0f172a; --mut:#64748b; --line:#e2e8f0; --bg:#f1f5f9; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--ink); }
  header { background:#fff; border-bottom:1px solid var(--line); padding:14px 18px; display:flex; align-items:center; gap:10px; position:sticky; top:0; }
  header b { font-size:18px; } header b span { color: var(--teal); }
  main { max-width: 1050px; margin: 0 auto; padding: 16px; }
  .tabs { display:flex; gap:6px; overflow:auto; margin-bottom:14px; }
  .tabs button { border:1px solid var(--line); background:#fff; border-radius:10px; padding:8px 14px; font-weight:600; cursor:pointer; white-space:nowrap; color:var(--mut); }
  .tabs button.on { background: var(--ink); color:#fff; border-color: var(--ink); }
  .card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:16px; margin-bottom:14px; }
  .grid { display:grid; grid-template-columns: repeat(auto-fit,minmax(150px,1fr)); gap:12px; }
  .stat { background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px; }
  .stat .l { font-size:12px; color:var(--mut); text-transform:uppercase; letter-spacing:.03em; }
  .stat .v { font-size:24px; font-weight:800; margin-top:2px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { font-size:12px; color:var(--mut); text-transform:uppercase; }
  input,select { width:100%; padding:9px 10px; border:1px solid var(--line); border-radius:10px; font-size:14px; }
  label { display:block; font-size:13px; color:var(--mut); margin:8px 0 3px; }
  button.act { border:0; border-radius:10px; padding:8px 12px; font-weight:700; cursor:pointer; }
  .p { background: var(--teal); color:#fff; } .d { background:#fee2e2; color:#b91c1c; } .g { background:#f1f5f9; color:#0f172a; }
  .row { display:flex; gap:8px; flex-wrap:wrap; align-items:end; }
  .badge { display:inline-block; border-radius:999px; padding:2px 8px; font-size:12px; font-weight:700; }
  .b-paid{background:#d1fae5;color:#047857;} .b-pending{background:#fef3c7;color:#92400e;} .b-other{background:#e2e8f0;color:#475569;}
  .muted{ color:var(--mut); font-size:13px; }
  .hidden{ display:none; }
  #login { max-width:340px; margin:8vh auto; }
  .warn { background:#fef3c7; color:#92400e; border-radius:10px; padding:10px 12px; font-size:14px; margin-bottom:12px; }
</style>
</head>
<body>
<div id="login" class="card hidden">
  <h2 style="margin:0 0 10px">Miku <span style="color:var(--teal)">OTP</span> Admin</h2>
  <label>Password</label>
  <input id="pw" type="password" onkeydown="if(event.key==='Enter')login()" />
  <div id="loginErr" class="muted" style="color:#b91c1c;margin-top:8px"></div>
  <button class="act p" style="margin-top:12px;width:100%" onclick="login()">Log in</button>
</div>

<div id="app" class="hidden">
  <header>
    <b>Miku <span>OTP</span></b> <span class="muted">Admin panel</span>
    <button class="act g" style="margin-left:auto" onclick="logout()">Log out</button>
  </header>
  <main>
    <div class="tabs" id="tabs"></div>
    <div id="view"></div>
  </main>
</div>

<script>
const F = (u,o)=>fetch(u,{headers:{'Content-Type':'application/json'},...o}).then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||r.status);return d;});
const inr = p => '₹'+(p/100).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
const esc = s => String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const dt = ms => new Date(ms).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'});
const el = document.getElementById.bind(document);
let TAB='Dashboard'; const TABS=['Dashboard','Deposits','Pricing','Orders','Users','Settings'];
let services=[];

async function login(){
  try{ await F('/api/login',{method:'POST',body:JSON.stringify({password:el('pw').value})}); boot(); }
  catch(e){ el('loginErr').textContent = e.message; }
}
async function logout(){ await F('/api/logout',{method:'POST'}); location.reload(); }

async function boot(){
  try{ await F('/api/overview'); }
  catch{ el('login').classList.remove('hidden'); el('app').classList.add('hidden'); return; }
  el('login').classList.add('hidden'); el('app').classList.remove('hidden');
  el('tabs').innerHTML = TABS.map(t=>'<button data-t="'+t+'" class="'+(t===TAB?'on':'')+'" onclick="go(\''+t+'\')">'+t+'</button>').join('');
  try{ services = (await F('/api/services')).services; }catch{}
  render();
}
function go(t){ TAB=t; document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===t)); render(); }
function render(){ ({Dashboard,Deposits,Pricing,Orders,Users,Settings}[TAB])(); }

async function Dashboard(){
  el('view').innerHTML='<div class="muted">Loading…</div>';
  const o = await F('/api/overview');
  const profit = o.today.salesPaise - o.today.costPaise;
  let warn='';
  if(o.grizzlyInrPaise!==null && o.grizzlyInrPaise < o.walletTotalPaise) warn+='<div class="warn">⚠️ GrizzlySMS balance is lower than customers\' total wallet. Top it up so orders don\'t fail.</div>';
  if(!o.gmail.configured) warn+='<div class="warn">⚠️ Gmail not configured — automatic deposits are OFF. Set GMAIL_USER / GMAIL_APP_PASSWORD.</div>';
  el('view').innerHTML = warn +
    '<div class="grid">'+
    stat('Sales today', inr(o.today.salesPaise), o.today.orders+' numbers')+
    stat('Profit today', inr(profit), 'cost '+inr(o.today.costPaise))+
    stat('Deposits today', inr(o.today.topupPaise))+
    stat('Users', o.users, 'wallets '+inr(o.walletTotalPaise))+
    stat('GrizzlySMS', o.grizzlyUsd===null?'—':'$'+o.grizzlyUsd.toFixed(2), o.grizzlyInrPaise===null?'':'≈ '+inr(o.grizzlyInrPaise))+
    stat('Gmail auto deposit', o.gmail.configured?'On':'Off', o.gmail.lastOk?('last '+dt(o.gmail.lastOk)):'')+
    '</div>';
}
const stat=(l,v,s)=>'<div class="stat"><div class="l">'+l+'</div><div class="v">'+v+'</div>'+(s?'<div class="muted">'+s+'</div>':'')+'</div>';

async function Deposits(){
  el('view').innerHTML='<div class="muted">Loading…</div>';
  const {deposits}=await F('/api/deposits?status=all');
  const rows=deposits.map(p=>'<tr><td>'+p.id+'</td><td>'+dt(p.created_at)+'</td><td>'+(p.username?('@'+esc(p.username)):p.telegram_id)+'</td><td><b>'+inr(p.amount_paise)+'</b></td><td>'+esc(p.utr||'—')+'</td><td>'+badge(p.status)+'</td><td>'+
    (p.status==='paid'?'':'<button class="act p" onclick="approve('+p.id+')">Approve</button> <button class="act d" onclick="reject('+p.id+')">Reject</button>')+'</td></tr>').join('');
  el('view').innerHTML='<div class="card"><h3>Deposits</h3><div class="muted">Matched automatically from FamApp emails. Approve by hand only if a payment did not match.</div><div style="overflow:auto"><table><tr><th>#</th><th>Date</th><th>User</th><th>Amount</th><th>UTR</th><th>Status</th><th></th></tr>'+(rows||'<tr><td colspan=7 class=muted>None</td></tr>')+'</table></div></div>';
}
async function approve(id){ const utr=prompt('Transaction ID / UTR (optional):')||''; try{ await F('/api/deposits/'+id+'/approve',{method:'POST',body:JSON.stringify({utr})}); Deposits(); }catch(e){ alert(e.message);} }
async function reject(id){ if(!confirm('Reject deposit #'+id+'?'))return; await F('/api/deposits/'+id+'/reject',{method:'POST'}); Deposits(); }

async function Orders(){
  el('view').innerHTML='<div class="muted">Loading…</div>';
  const {orders}=await F('/api/orders');
  const rows=orders.map(o=>'<tr><td>'+o.id+'</td><td>'+dt(o.created_at)+'</td><td>'+(o.username?('@'+esc(o.username)):o.telegram_id)+'</td><td>'+esc(o.service_name)+'<div class=muted>'+esc(o.country_name)+'</div></td><td>'+(o.phone?('+'+esc(o.phone)):'—')+'</td><td>'+(JSON.parse(o.codes).map(esc).join(', ')||'—')+'</td><td>'+inr(o.price_paise)+'</td><td>'+badge(o.status)+'</td></tr>').join('');
  el('view').innerHTML='<div class="card"><h3>Orders</h3><div style="overflow:auto"><table><tr><th>#</th><th>Date</th><th>User</th><th>Service</th><th>Number</th><th>OTP</th><th>Price</th><th>Status</th></tr>'+(rows||'<tr><td colspan=8 class=muted>None</td></tr>')+'</table></div></div>';
}

async function Users(){
  el('view').innerHTML='<div class="card"><div class="row"><div style="flex:1"><input id="uq" placeholder="Search @username, name or Telegram ID" oninput="loadUsers()"></div></div><div id="ut" style="overflow:auto;margin-top:10px"></div></div>';
  loadUsers();
}
async function loadUsers(){
  const q=encodeURIComponent(el('uq')?.value||'');
  const {users}=await F('/api/users?q='+q);
  const rows=users.map(u=>'<tr><td>'+u.id+'</td><td>'+(u.username?('@'+esc(u.username)):'')+'<div class=muted>'+esc(u.first_name||'')+' · '+u.telegram_id+'</div></td><td><b>'+inr(u.balance_paise)+'</b></td><td>'+inr(u.topup_paise)+'</td><td>'+u.orders+'</td><td>'+(u.blocked?'<span class="badge b-other">blocked</span>':'')+'</td><td><button class="act g" onclick="adjust('+u.id+')">± Balance</button> <button class="act d" onclick="block('+u.id+','+(u.blocked?0:1)+')">'+(u.blocked?'Unblock':'Block')+'</button></td></tr>').join('');
  el('ut').innerHTML='<table><tr><th>#</th><th>User</th><th>Balance</th><th>Topups</th><th>Nums</th><th></th><th></th></tr>'+(rows||'<tr><td colspan=7 class=muted>None</td></tr>')+'</table>';
}
async function adjust(id){ const v=prompt('Change balance by ₹ (minus to deduct, e.g. -20):'); if(!v)return; const note=prompt('Reason (shown to user):')||''; try{ await F('/api/users/'+id+'/balance',{method:'POST',body:JSON.stringify({amount:Number(v),note})}); loadUsers(); }catch(e){ alert(e.message);} }
async function block(id,b){ await F('/api/users/'+id+'/block',{method:'POST',body:JSON.stringify({blocked:b})}); loadUsers(); }

async function Pricing(){
  el('view').innerHTML='<div class="muted">Loading…</div>';
  const {rules}=await F('/api/rules');
  const opts='<option value="default">Default (cost × rate)</option><option value="plus">Plus ₹ (add on top)</option><option value="markup">Markup %</option><option value="fixed">Fixed ₹ (flat)</option>';
  const svcList = services.map(s=>'<option value="'+esc(s.code)+'">'+esc(s.name)+' ('+esc(s.code)+')</option>').join('');
  const rows=rules.map(r=>'<tr><td>'+esc(r.service)+'</td><td>'+esc(r.country)+'</td><td>'+r.mode+(r.mode==='default'?'':' '+r.value)+'</td><td>'+(r.hidden?'Yes':'No')+'</td><td><button class="act d" onclick="delRule('+r.id+')">Delete</button></td></tr>').join('');
  el('view').innerHTML=
    '<div class="card"><h3>Add / update rule</h3>'+
    '<div class="muted">Default selling price = GrizzlySMS cost × USD→INR rate (Settings). A rule overrides it for one service (all countries with <b>*</b>, or one country code). WhatsApp has a default <b>Plus ₹40</b> rule.</div>'+
    '<div class="row" style="margin-top:10px">'+
    '<div style="flex:2"><label>Service</label><input id="rsvc" list="svclist" placeholder="wa  (or * for all)"><datalist id="svclist">'+svcList+'</datalist></div>'+
    '<div style="flex:1"><label>Country code</label><input id="rctry" value="*" placeholder="* or 22"></div>'+
    '<div style="flex:1"><label>Mode</label><select id="rmode">'+opts+'</select></div>'+
    '<div style="flex:1"><label>Value</label><input id="rval" type="number" value="40"></div>'+
    '<div><label>Hidden</label><select id="rhid"><option value="0">No</option><option value="1">Yes</option></select></div>'+
    '<div><button class="act p" onclick="saveRule()">Save</button></div>'+
    '</div></div>'+
    '<div class="card"><h3>Current rules</h3><div style="overflow:auto"><table><tr><th>Service</th><th>Country</th><th>Rule</th><th>Hidden</th><th></th></tr>'+(rows||'<tr><td colspan=5 class=muted>No rules</td></tr>')+'</table></div></div>';
}
async function saveRule(){ try{ await F('/api/rules',{method:'POST',body:JSON.stringify({service:el('rsvc').value.trim(),country:el('rctry').value.trim()||'*',mode:el('rmode').value,value:Number(el('rval').value||0),hidden:el('rhid').value==='1'})}); Pricing(); }catch(e){ alert(e.message);} }
async function delRule(id){ if(!confirm('Delete rule?'))return; await F('/api/rules/'+id,{method:'DELETE'}); Pricing(); }

const SET=[['usd_inr_rate','USD → INR rate','number'],['global_markup_pct','Global markup %','number'],['min_topup_inr','Minimum deposit (₹)','number'],['max_topup_inr','Maximum deposit (₹)','number'],['payment_window_min','Deposit QR valid (minutes)','number'],['order_timeout_min','Number valid (minutes)','number'],['upi_id','UPI ID (receives money)','text'],['upi_name','UPI payee name','text'],['welcome_text','Welcome note (optional)','text']];
async function Settings(){
  const {settings}=await F('/api/settings');
  el('view').innerHTML='<div class="card"><h3>Settings</h3>'+SET.map(([k,l,t])=>'<label>'+l+'</label><input id="s_'+k+'" type="'+t+'" value="'+esc(settings[k]??'')+'">').join('')+'<button class="act p" style="margin-top:14px" onclick="saveSettings()">Save settings</button> <span id="sok" class="muted"></span></div>';
}
async function saveSettings(){ const body={}; SET.forEach(([k])=>body[k]=el('s_'+k).value); try{ await F('/api/settings',{method:'POST',body:JSON.stringify(body)}); el('sok').textContent='Saved ✓'; }catch(e){ alert(e.message);} }

function badge(s){ const c=s==='paid'?'b-paid':s==='pending'?'b-pending':'b-other'; return '<span class="badge '+c+'">'+s+'</span>'; }

boot();
</script>
</body>
</html>`;
