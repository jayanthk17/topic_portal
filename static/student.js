const $=id=>document.getElementById(id);let topics=[],max=0,student=null,csrf='';
function setMessage(msg,bad=false){$('message').textContent=msg;$('message').className=bad?'bad':'good'}
function member(){const i=$('members').children.length+1;const div=document.createElement('div');div.className='member';div.innerHTML=`<strong>Member ${i}</strong><div class="member-grid"><label>Full name<input class="name" maxlength="100" required placeholder="Student name"></label><label>USN<input class="usn" maxlength="30" required placeholder="e.g. 1JT23IS001"></label></div>`;$('members').append(div);if(i===1&&student){div.querySelector('.name').value=student.name;div.querySelector('.usn').value=student.usn;div.querySelectorAll('input').forEach(input=>input.readOnly=true)}}
function selected(){return topics.find(t=>t.id===Number($('topic').value))}
function sync(){const t=selected();max=t&&!t.booked?t.max_members:0;$('availability').textContent=!t?'Select a topic to continue':t.booked?'🔴 Already selected — unavailable':`🟢 Available — maximum ${max} student${max===1?'':'s'} per group`;$('availability').className=t?.booked?'bad':'good';$('limit').textContent=max?`Maximum ${max} members`:'No available topic selected';$('add').disabled=!max||$('members').children.length>=max;$('remove').disabled=$('members').children.length<=1;$('form').querySelector('button[type=submit]').disabled=!max;while($('members').children.length>max&&$('members').children.length>1)$('members').lastElementChild.remove()}
async function load(){try{const r=await fetch('/api/topics');topics=await r.json();const previous=$('topic').value;$('topic').replaceChildren(new Option('Choose a project topic',''));topics.forEach(t=>{const o=new Option(`${t.booked?'🔴':'🟢'} ${t.title} — ${t.booked?'Already selected':`Max ${t.max_members} members`}`,t.id);o.disabled=!!t.booked;$('topic').add(o)});if(topics.some(t=>String(t.id)===previous&&!t.booked))$('topic').value=previous;sync()}catch{setMessage('Could not load topics. Try refreshing.',true)}}
$('topic').addEventListener('change',sync);$('add').onclick=()=>{if($('members').children.length<max)member();sync()};$('remove').onclick=()=>{if($('members').children.length>1)$('members').lastElementChild.remove();sync()};$('form').addEventListener('submit',async e=>{e.preventDefault();const t=selected();if(!t||t.booked)return setMessage('Choose an available topic.',true);const members=[...$('members').children].map(x=>({name:x.querySelector('.name').value.trim(),usn:x.querySelector('.usn').value.trim()}));if(members.length>max)return setMessage('Too many members.',true);const btn=$('form').querySelector('button[type=submit]');btn.disabled=true;try{const r=await fetch('/api/register',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({topic_id:t.id,members})});const d=await r.json();setMessage(d.message||d.error,!r.ok);if(r.ok){$('form').reset();$('members').replaceChildren();member()}await load()}catch{setMessage('Connection error. Please try again.',true)}finally{sync()}});


async function start(){try{const r=await fetch('/api/student/session');const d=await r.json();if (!d.logged_in) {
  studentLoginExpired();
  return;
}student={name:d.name,usn:d.usn};csrf=d.csrf;setStudentExpiry(d.expires_at);$('studentIdentity').textContent=d.name+' ('+d.usn+')';member();await load();setInterval(load,15000)}catch{setMessage('Could not verify student login.',true)}}
$('studentLogout').onclick=async()=>{await fetch('/api/student/logout',{method:'POST',headers:{'X-CSRF-Token':csrf}});location.href='/student/login'};
start();

let studentExpiryTimer = null;
let studentExpiryShown = false;

function studentLoginExpired() {
  if (studentExpiryShown) return;
  studentExpiryShown = true;

  clearTimeout(studentExpiryTimer);

  alert(
    "Your 5-minute student login session has expired.\n" +
    "Please log in again to continue."
  );

  window.location.replace("/student/login");
}

function setStudentExpiry(expiresAt) {
  if (!expiresAt) {
    studentLoginExpired();
    return;
  }

  clearTimeout(studentExpiryTimer);

  const remaining = expiresAt * 1000 - Date.now();

  if (remaining <= 0) {
    studentLoginExpired();
    return;
  }

  studentExpiryTimer = setTimeout(
    studentLoginExpired,
    remaining
  );
}



document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !studentExpiryShown) {
    fetch("/api/student/session")
      .then(r => r.json())
      .then(d => {
        if (!d.logged_in) {
          studentLoginExpired();
        } else {
          load();
        }
      })
      .catch(() => {});
  }
});

window.addEventListener("focus", () => {
  if (!studentExpiryShown) {
    load();
  }
});
