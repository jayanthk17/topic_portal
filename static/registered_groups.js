const list = document.getElementById('publicRegistrations');
const status = document.getElementById('status');
const count = document.getElementById('count');
const dateFormat = new Intl.DateTimeFormat('en-IN', {timeZone:'Asia/Kolkata',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:true});
function node(tag, className, content) {const e=document.createElement(tag);if(className)e.className=className;if(content!==undefined)e.textContent=content;return e;}
async function refreshRegistrations(){
  try {
    const response=await fetch('/api/registered-groups',{cache:'no-store'});
    if(!response.ok)throw new Error('Could not load registrations.');
    const groups=await response.json();
    list.replaceChildren();
    count.textContent=`${groups.length} registered group${groups.length===1?'':'s'}`;
    status.textContent=groups.length?'':'No groups registered yet.';
    for(const group of groups){
      const card=node('article','record');
      card.append(node('div','record-title',group.topic));
      const time=new Date(group.created_at);
      card.append(node('small','',Number.isNaN(time.getTime())?'Registration time unavailable':`Registered: ${dateFormat.format(time)} IST`));
      card.append(node('p','',`Members: ${group.members.join(', ') || 'Not listed'}`));
      list.append(card);
    }
  }catch(err){status.textContent=err.message;status.className='bad';}
}
refreshRegistrations();setInterval(refreshRegistrations,15000);

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    refreshRegistrations();
  }
});

window.addEventListener("focus", () => {
  refreshRegistrations();
});
