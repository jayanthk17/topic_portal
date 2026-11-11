const $=id=>document.getElementById(id);
$('loginForm').onsubmit=async e=>{
  e.preventDefault();
  const msg=$('authMessage'); msg.textContent='';
  try {
    const r=await fetch('/api/student/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usn:$('loginUsn').value,password:$('loginPassword').value})});
    const d=await r.json();
    if(!r.ok)throw Error(d.error||'Sign in failed');
    location.href='/';
  }catch(err){msg.className='bad';msg.textContent=err.message}
};
