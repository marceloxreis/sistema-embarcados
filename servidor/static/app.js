'use strict';
const $ = id => document.getElementById(id);
let adminPin = '', overview = null, timer = null, filterTimer = null, loading = false;
const labels = {
  device_boot:'Inicialização',storage_error:'Erro de armazenamento',user_enrolled:'Pessoa cadastrada',
  user_disabled:'Pessoa desativada',user_enabled:'Pessoa reativada',password_reset:'Senha redefinida',
  admin_login:'Administrador autenticado',access_granted:'Acesso autorizado',access_denied:'Acesso negado',
  door_opened:'Porta aberta',door_closed:'Porta fechada',entry_expired:'Prazo de abertura expirou',
  door_timeout:'Porta aberta por mais de 5 min',forced_open:'Abertura sem autorização',enroll_failed:'Falha no cadastro'
};
const methods = {password:'Senha',fingerprint:'Digital',admin:'Administrador',keypad:'Teclado',system:'Sistema',sensor:'Sensor',usb:'USB',web:'Página web'};
const reasons = {ok:'Concluído',device_busy:'ESP32 ocupado: tente novamente após sair do cadastro.',unknown_user:'ID inexistente',invalid_pin:'Senha inválida',pin_in_use:'Senha já pertence a outro ID',storage_error:'Falha ao salvar',inactive_or_unknown:'Cadastro inativo ou desconhecido',unknown_finger:'Digital desconhecida',sensor_error:'Erro no leitor',simulation:'Acionamento elétrico desabilitado',actuator_enabled:'Acionamento elétrico habilitado',open_at_boot:'Porta aberta ao iniciar'};
const idLabel = id => `ID ${String(id).padStart(3,'0')}`;
const dateLabel = seconds => new Date(seconds * 1000).toLocaleString('pt-BR');
function message(text, error=false){ $('message').textContent=text; $('message').className=error?'error':'success'; }
async function api(path,body){
  const response=await fetch(path,{method:body?'POST':'GET',headers:{'X-Admin-Pin':adminPin,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || 'Falha na consulta.');
  return data;
}
function cell(row,text){ const td=document.createElement('td'); td.textContent=text; row.append(td); }
function renderEvents(){
  const events=overview.events;
  $('events').replaceChildren();
  for(const e of events){
    const tr=document.createElement('tr');
    const when=e.epoch?dateLabel(e.epoch):`Sem horário · +${Math.floor(e.uptime_ms/1000)}s · sessão ${e.boot_id.slice(-6)}`;
    cell(tr,when);cell(tr,e.user_id?idLabel(e.user_id):'—');cell(tr,labels[e.type]||e.type);cell(tr,methods[e.method]||'—');cell(tr,reasons[e.reason]||e.reason||'—');
    $('events').append(tr);
  }
  if(!events.length){ const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=5;td.textContent='Nenhum evento recebido para este filtro.';tr.append(td);$('events').append(tr); }
}
function render(){
  const device=overview.devices[0];
  if(device){
    const fresh=overview.server_time-device.seen_at<30;
    $('device-status').textContent=fresh?'ESP32 conectado':'Sem contato recente';
    $('device-detail').textContent=`Último contato: ${dateLabel(device.seen_at)} · relógio ${device.clock_synced?'sincronizado':'sem sincronização'}.`;
    $('queued').textContent=device.queued;
  }else{$('device-status').textContent='Sem conexão registrada';$('device-detail').textContent='Aguardando o primeiro contato do ESP32.';$('queued').textContent='—';}
  $('user-count').textContent=`${overview.users.length} / 100`;
  const active=overview.users.filter(u=>u.active).length;
  $('active-count').textContent=`${active} ativos · ${overview.users.length-active} inativos`;
  const selected=$('user-id').value;
  $('user-id').replaceChildren(new Option('Selecione um ID',''));
  for(const u of overview.users) $('user-id').add(new Option(`${idLabel(u.user_id)} · ${u.active?'ativo':'inativo'}`,String(u.user_id)));
  $('user-id').value=selected;
  $('commands').replaceChildren();
  for(const c of overview.commands){
    const li=document.createElement('li'),strong=document.createElement('strong'),p=document.createElement('p');
    const status={pending:'Pendente no ESP32',applied:'Aplicada',rejected:'Recusada'}[c.status]||c.status;
    strong.textContent=`${idLabel(c.user_id)} · ${status}`;
    p.textContent=`${dateLabel(c.created_at)}${c.reason?' · '+(reasons[c.reason]||c.reason):''}`;
    li.append(strong,p);$('commands').append(li);
  }
  if(!overview.commands.length){const li=document.createElement('li');li.textContent='Nenhuma redefinição solicitada.';$('commands').append(li);}
  $('updated').textContent=`Consulta: ${dateLabel(overview.server_time)}`;renderEvents();
}
async function refresh(){
  if(loading||!adminPin)return;
  const filter=$('filter-id').value;
  if(filter && (!Number.isInteger(Number(filter)) || Number(filter)<1 || Number(filter)>100)){
    message('O filtro de ID deve estar entre 1 e 100.',true);return;
  }
  loading=true;$('refresh').disabled=true;
  try{const data=await api('/api/admin/overview'+(filter?'?user_id='+encodeURIComponent(filter):''));if(filter===$('filter-id').value){overview=data;render();}}
  catch(e){message(e.message,true);}
  finally{loading=false;$('refresh').disabled=false;if(filter!==$('filter-id').value)refresh();}
}
$('login-form').addEventListener('submit',async e=>{
  e.preventDefault();adminPin=$('admin-pin').value;
  const button=e.target.querySelector('button');button.disabled=true;
  try{overview=await api('/api/admin/overview');$('login').hidden=true;$('dashboard').hidden=false;$('admin-pin').value='';message('');render();timer=setInterval(()=>{if(!document.hidden)refresh();},5000);$('refresh').focus();}
  catch(error){adminPin='';message(error.message,true);}
  finally{button.disabled=false;}
});
$('logout').addEventListener('click',()=>{clearInterval(timer);clearTimeout(filterTimer);adminPin='';overview=null;$('reset-form').reset();$('filter-id').value='';$('dashboard').hidden=true;$('login').hidden=false;message('Sessão encerrada.');$('admin-pin').focus();});
$('refresh').addEventListener('click',refresh);
$('filter-id').addEventListener('input',()=>{clearTimeout(filterTimer);filterTimer=setTimeout(refresh,250);});
$('reset-form').addEventListener('submit',async e=>{
  e.preventDefault();const pin=$('new-pin').value,confirmation=$('confirm-pin').value;
  if(pin!==confirmation){message('As duas senhas devem ser iguais.',true);$('confirm-pin').focus();return;}
  const button=e.target.querySelector('button');button.disabled=true;
  const user=overview.users.find(u=>u.user_id===Number($('user-id').value));
  try{await api('/api/admin/reset',{device:user.device,user_id:user.user_id,pin,confirmation});$('new-pin').value='';$('confirm-pin').value='';message('Solicitação pendente. Aguarde a confirmação do ESP32 em “Alterações de senha”.');await refresh();}
  catch(error){message(error.message,true);}
  finally{button.disabled=false;}
});
