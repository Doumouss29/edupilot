self.addEventListener('push',event=>{
  let data={title:'EduPilot',body:'Nouvelle notification',url:'/'};
  try{if(event.data)data={...data,...event.data.json()};}catch(e){}
  const path=typeof data.url==='string'&&data.url.startsWith('/')&&!data.url.startsWith('//')?data.url:'/';
  event.waitUntil(self.registration.showNotification(String(data.title||'EduPilot'),{
    body:String(data.body||'Nouvelle notification').slice(0,350),
    icon:'/static/edupilot-192.png?v=official-20261018d',badge:'/static/edupilot-192.png?v=official-20261018d',
    tag:'edupilot-'+Date.now(),data:{url:path}
  }));
});
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const url=new URL(event.notification.data?.url||'/',self.location.origin);
  event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(all=>{
    for(const client of all){if(new URL(client.url).origin===url.origin){return client.navigate(url.href).then(c=>c.focus());}}
    return clients.openWindow(url.href);
  }));
});
