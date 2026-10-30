'use strict';
const $ = id => document.getElementById(id);
let adminPin = '', overview = null, timer = null, filterTimer = null, loading = false, photoUrl = null, lastSnapshot = '', noticeUntil = 0, messageSource = 'other', sessionId = 0;
const labels = {
  device_boot:'Inicialização',storage_error:'Erro de armazenamento',user_enrolled:'Pessoa cadastrada',
  user_disabled:'Pessoa desativada',user_enabled:'Pessoa reativada',password_reset:'Senha redefinida',
  admin_login:'Administrador autenticado',access_granted:'Acesso autorizado',access_denied:'Acesso negado',
  door_opened:'Porta aberta',door_closed:'Porta fechada',entry_expired:'Prazo de abertura expirou',
  door_timeout:'Porta aberta por mais de 5 min',forced_open:'Abertura sem autorização',enroll_failed:'Falha no cadastro'
};
const methods = {password:'Senha',fingerprint:'Digital',admin:'Administrador',keypad:'Teclado',system:'Sistema',sensor:'Sensor',usb:'USB',web:'Página web'};
const reasons = {ok:'Concluído',device_busy:'Controlador ocupado: tente novamente após fechar a porta e sair do cadastro.',unknown_user:'ID inexistente',invalid_pin:'Senha inválida',pin_in_use:'Senha já pertence a outro ID',storage_error:'Falha ao salvar',inactive_or_unknown:'Cadastro inativo ou desconhecido',unknown_finger:'Digital desconhecida',sensor_error:'Erro no leitor',simulation:'Acionamento elétrico desabilitado',actuator_enabled:'Acionamento elétrico habilitado',open_at_boot:'Porta aberta ao iniciar',photo_unavailable:'Foto indisponível',expired:'Expirada (sem confirmação em 24 h)'};
const idLabel = id => `ID ${String(id).padStart(3,'0')}`;
const dateLabel = seconds => new Date(seconds * 1000).toLocaleString('pt-BR');
function message(text, error=false, source='other'){ $('message').textContent=text; $('message').className=error?'error':'success'; messageSource=source; }
function failure(text,status){ const error=new Error(text); error.status=status; return error; }
async function api(path,body){
  const response=await fetch(path,{method:body?'POST':'GET',headers:{'X-Admin-Pin':adminPin,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined}).catch(()=>{throw failure('Servidor indisponível; verifique a conexão.',0);});
  let data=null; try{data=await response.json();}catch(error){data=null;}
  if(!response.ok) throw failure((data&&data.error) || (response.status===503?'Banco de dados indisponível; tente novamente.':'Falha na consulta.'),response.status);
  if(data===null) throw failure('Resposta inválida do servidor.',response.status);
  return data;
}
function cell(row,text){ const td=document.createElement('td'); td.textContent=text; row.append(td); }
function closePhoto(){ $('photo-view').hidden=true; $('photo-image').removeAttribute('src'); if(photoUrl) URL.revokeObjectURL(photoUrl); photoUrl=null; }
function renderEvents(){
  const events=overview.events;
  $('events').replaceChildren();
  for(const e of events){
    const tr=document.createElement('tr');
    const when=e.epoch?dateLabel(e.epoch):`Sem horário · +${Math.floor(e.uptime_ms/1000)}s · sessão ${e.boot_id.slice(-6)}`;
    cell(tr,when);cell(tr,e.user_id?idLabel(e.user_id):'—');cell(tr,labels[e.type]||e.type);cell(tr,methods[e.method]||'—');cell(tr,reasons[e.reason]||e.reason||'—');
    const photoCell=document.createElement('td');
    if(e.has_photo){
      const button=document.createElement('button'); button.type='button';button.textContent='Ver foto';
      button.addEventListener('click',async()=>{
        button.disabled=true;
        const sessionPin=adminPin;
        try{
          const response=await fetch('/api/admin/photo?event_id='+encodeURIComponent(e.event_id),{headers:{'X-Admin-Pin':sessionPin}}).catch(()=>{throw failure('Servidor indisponível; verifique a conexão.',0);});
          if(!response.ok) throw new Error('Não foi possível carregar a foto.');
          const blob=await response.blob(); if(!sessionPin || sessionPin!==adminPin) return;
          closePhoto(); photoUrl=URL.createObjectURL(blob); $('photo-image').src=photoUrl;
          $('photo-image').alt=`Foto do ${idLabel(e.user_id)}`; $('photo-label').textContent=`Foto do ${idLabel(e.user_id)} · ${when}`;
          $('photo-view').hidden=false;
          $('photo-label').scrollIntoView({block:'nearest'}); $('photo-label').focus();
        }catch(error){message(error.message,true);}
        finally{button.disabled=false;}
      });
      photoCell.append(button);
    }else photoCell.textContent='—';
    tr.append(photoCell);
    $('events').append(tr);
  }
  if(!events.length){ const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=6;td.textContent='Nenhum evento recebido para este filtro.';tr.append(td);$('events').append(tr); }
}
function render(){
  const device=overview.devices[0];
  if(device){
    const fresh=overview.server_time-device.seen_at<30;
    $('device-status').textContent=fresh?'ESP32 conectado':'Sem contato recente';
    $('device-detail').textContent=`Último contato: ${dateLabel(device.seen_at)} · relógio ${device.clock_synced?'sincronizado':'sem sincronização'}.`;
    $('queued').textContent=device.queued;
    // Totais = acumulado de reinicializações anteriores da CAM (*_prev) + valor atual.
    // "dropped" é reservado no firmware (sempre 0): fica armazenado, mas não aparece.
    const total=name=>Math.min(Number.MAX_SAFE_INTEGER,(Number(device[name])||0)+(Number(device[name+'_prev'])||0));
    const rejected=total('rejected'),photoRejected=total('photo_rejected');
    const lostEarlier=(Number(device.rejected_prev)||0)+(Number(device.photo_rejected_prev)||0)>0;
    const lost=rejected>0||photoRejected>0;
    $('device-counters').hidden=false;
    $('device-counters').textContent=`Descartados após rejeição definitiva: ${rejected} (totais desde o início do histórico, somando reinicializações do ESP32).`;
    $('device-photo-loss').hidden=false;
    $('device-photo-loss').textContent=`Eventos aceitos sem foto por rejeição definitiva: ${photoRejected}.`;
    $('device-loss').hidden=!lost;
    if(lost){
      const notes=[];
      if(rejected>0) notes.push('Eventos descartados após rejeição definitiva podem estar ausentes do histórico desta página.');
      if(photoRejected>0) notes.push('Eventos aceitos sem foto aparecem no histórico sem imagem.');
      $('device-loss').textContent=`Atenção: o ESP32 informou falhas no registro de eventos. ${notes.join(' ')}${lostEarlier?' Há perdas acumuladas de reinicializações anteriores; este aviso continua enquanto o total for maior que zero.':''}`;
    }else $('device-loss').textContent='';
  }else{$('device-status').textContent='Sem conexão registrada';$('device-detail').textContent='Aguardando o primeiro contato do ESP32.';$('queued').textContent='—';$('device-counters').hidden=true;$('device-photo-loss').hidden=true;$('device-loss').hidden=true;}
  $('user-count').textContent=`${overview.users.length} / 100`;
  const active=overview.users.filter(u=>u.active).length;
  $('active-count').textContent=`${active} ativos · ${overview.users.length-active} inativos`;
  // Não recria o seletor enquanto o usuário o usa; o blur (abaixo) aplica a lista atual.
  if(document.activeElement!==$('user-id')){
    const selected=$('user-id').value;
    $('user-id').replaceChildren(new Option('Selecione um ID',''));
    for(const u of overview.users) $('user-id').add(new Option(`${idLabel(u.user_id)} · ${u.active?'ativo':'inativo'}`,String(u.user_id)));
    $('user-id').value=selected;
  }
  $('commands').replaceChildren();
  for(const c of overview.commands){
    const li=document.createElement('li'),strong=document.createElement('strong'),p=document.createElement('p');
    const status={pending:'Pendente no Mega',applied:'Aplicada',rejected:'Recusada'}[c.status]||c.status;
    strong.textContent=`${idLabel(c.user_id)} · ${status}`;
    p.textContent=`${dateLabel(c.created_at)}${c.reason?' · '+(reasons[c.reason]||c.reason):''}`;
    li.append(strong,p);$('commands').append(li);
  }
  if(!overview.commands.length){const li=document.createElement('li');li.textContent='Nenhuma redefinição solicitada.';$('commands').append(li);}
  $('updated').textContent=`Consulta: ${dateLabel(overview.server_time)}`;renderEvents();
}
async function refresh(){
  if(loading||!adminPin)return;
  const filter=$('filter-id').value, session=sessionId; // sessão capturada antes do await
  if(filter && (!Number.isInteger(Number(filter)) || Number(filter)<1 || Number(filter)>100)){
    message('O filtro de ID deve estar entre 1 e 100.',true,'refresh');return;
  }
  loading=true;$('refresh').disabled=true;
  try{
    const data=await api('/api/admin/overview'+(filter?'?user_id='+encodeURIComponent(filter):''));
    if(session!==sessionId||!adminPin) return; // sessão encerrada ou trocada durante a consulta: não repopula o painel
    if(filter===$('filter-id').value){
      // Re-renderiza só se mudou: server_time fica fora da chave (vai só no rodapé); frescor do ESP32 entra nela.
      const device=data.devices[0], snapshot=JSON.stringify({...data,server_time:0,fresh:device?data.server_time-device.seen_at<30:null});
      overview=data;
      if(snapshot!==lastSnapshot){lastSnapshot=snapshot;render();}else $('updated').textContent=`Consulta: ${dateLabel(data.server_time)}`;
      // Limpa só o aviso deste próprio refresh ou a confirmação do reset já expirada; erros de outras ações ficam até a próxima ação.
      if(messageSource==='refresh'||(messageSource==='notice'&&Date.now()>=noticeUntil)) message('');
    }
  }
  catch(e){
    if(session!==sessionId||!adminPin) return; // sessão encerrada ou trocada: erro atrasado não sobrescreve o aviso nem chama logout() de novo
    if(e.status===401) logout('Senha recusada ou alterada; entre novamente.',true);
    else if(e.status===429) logout('Muitas tentativas; aguarde um minuto e entre novamente.',true);
    else message(e.message,true,'refresh');
  }
  finally{loading=false;$('refresh').disabled=false;if(filter!==$('filter-id').value)refresh();}
}
$('login-form').addEventListener('submit',async e=>{
  e.preventDefault();adminPin=$('admin-pin').value;
  const button=e.target.querySelector('button');button.disabled=true;
  try{overview=await api('/api/admin/overview');$('login').hidden=true;$('dashboard').hidden=false;$('admin-pin').value='';message('');render();timer=setInterval(()=>{if(!document.hidden)refresh();},5000);$('refresh').focus();}
  catch(error){adminPin='';message(error.message,true);}
  finally{button.disabled=false;}
});
function logout(text='Sessão encerrada.',error=false){clearInterval(timer);clearTimeout(filterTimer);sessionId++;adminPin='';overview=null;lastSnapshot='';noticeUntil=0;closePhoto();$('reset-form').reset();$('filter-id').value='';$('dashboard').hidden=true;$('login').hidden=false;message(text,error);$('admin-pin').focus();}
$('logout').addEventListener('click',()=>logout());
$('user-id').addEventListener('blur',()=>{if(overview)render();});
$('photo-close').addEventListener('click',closePhoto);
$('refresh').addEventListener('click',refresh);
$('filter-id').addEventListener('input',()=>{clearTimeout(filterTimer);filterTimer=setTimeout(refresh,250);});
$('reset-form').addEventListener('submit',async e=>{
  e.preventDefault();const pin=$('new-pin').value,confirmation=$('confirm-pin').value;
  if(pin!==confirmation){message('As duas senhas devem ser iguais.',true);$('confirm-pin').focus();return;}
  const user=overview.users.find(u=>u.user_id===Number($('user-id').value));
  if(!user){message('Selecione um ID válido.',true);$('user-id').focus();return;}
  const button=e.target.querySelector('button');button.disabled=true;
  try{await api('/api/admin/reset',{device:user.device,user_id:user.user_id,pin,confirmation});$('new-pin').value='';$('confirm-pin').value='';noticeUntil=Date.now()+15000;message('Solicitação pendente. Aguarde a confirmação do ESP32 em “Alterações de senha”.',false,'notice');await refresh();}
  catch(error){message(error.message,true);}
  finally{button.disabled=false;}
});
