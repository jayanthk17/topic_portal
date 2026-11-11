
const $ = id => document.getElementById(id);
let csrf = "";

let adminExpiryTimer = null;
let adminExpiryShown = false;



function adminLoginExpired() {
  if (adminExpiryShown) return;

  adminExpiryShown = true;
  clearTimeout(adminExpiryTimer);
  csrf = "";

  alert(
    "Your 15-minute admin session has expired.\n" +
    "Please sign in again."
  );

  // Show login form without repeatedly reloading /admin
  $("dashboard").hidden = true;
  $("loginPanel").hidden = false;
  $("password").value = "";
}


function setAdminExpiry(expiresAt) {
  clearTimeout(adminExpiryTimer);

  if (!expiresAt) return;

  const remaining = expiresAt * 1000 - Date.now();

  if (remaining <= 0) {
    adminLoginExpired();
    return;
  }

  adminExpiryShown = false;

  adminExpiryTimer = setTimeout(
    adminLoginExpired,
    remaining
  );
}



async function api(url, method = "GET", body) {
  const r = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const d = await r.json();
  if (!r.ok) throw Error(d.error || "Request failed");
  return d;
}

function message(id, text, bad = false) {
  $(id).textContent = text;
  $(id).className = bad ? "bad" : "good";
}

function el(tag, cls = "", text) {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}




async function sessionCheck() {
  const s = await api("/api/admin/session");

  csrf = s.csrf || "";

  if (s.logged_in) {
    $("loginPanel").hidden = true;
    $("dashboard").hidden = false;

    setAdminExpiry(s.expires_at);
    await refresh();
  } else {
    clearTimeout(adminExpiryTimer);
    adminExpiryShown = false;

    $("dashboard").hidden = true;
    $("loginPanel").hidden = false;
  }
}





$("login").onsubmit = async e => {
  e.preventDefault();

  try {
    const d = await api("/api/admin/login", "POST", {
      username: $("username").value,
      password: $("password").value
    });

    csrf = d.csrf;
    adminExpiryShown = false;

    await sessionCheck();
  } catch (err) {
    message("loginMsg", err.message, true);
  }
};


$("logout").onclick = async () => {
  await api("/api/admin/logout", "POST");
  csrf = "";
  clearTimeout(adminExpiryTimer);
  await sessionCheck();
};

$("addTopic").onsubmit = async e => {
  e.preventDefault();
  try {
    await api("/api/admin/topics", "POST", {
      title: $("newTitle").value,
      max_members: Number($("newMax").value)
    });
    $("newTitle").value = "";
    message("topicMsg", "Topic added.");
    await refresh();
  } catch (err) {
    message("topicMsg", err.message, true);
  }
};

async function refresh() {
  const [topics, regs, students] = await Promise.all([
    api("/api/topics"),
    api("/api/admin/registrations"),
    api("/api/admin/students")
  ]);

  const topicList = $("topicList");
  topicList.replaceChildren();

let clearButton = $("clearRegistrationsBtn");

if (!clearButton) {
  clearButton = el(
    "button",
    "secondary",
    "Clear All Registrations"
  );

  clearButton.id = "clearRegistrationsBtn";
  clearButton.type = "button";
  topicList.before(clearButton);

  clearButton.onclick = async () => {
    if (!confirm(
      "Delete ALL registered groups and member details? " +
      "Topics will become available again. " +
      "Student login accounts remain. " +
      "This cannot be undone."
    )) return;

    const admin_password = prompt(
      "Enter your ADMIN login password:"
    );

    if (admin_password === null) return;

    try {
      const result = await api(
        "/api/admin/registrations/clear",
        "POST",
        { admin_password }
      );

      message(
        "topicMsg",
        `${result.cleared} registration(s) cleared successfully.`
      );

      await refresh();
    } catch (err) {
      message("topicMsg", err.message, true);
    }
  };
}








  topics.forEach(t => {
    const row = el("div", "record");
    row.append(el("strong", "", t.title));
    row.append(
      el("span", "pill", t.booked ? "🔴 Booked" : "🟢 Available")
    );

    const form = el("div", "edit-row");
    const title = el("input");
    title.value = t.title;

    const size = el("input");
    size.type = "number";
    size.min = 1;
    size.max = 30;
    size.value = t.max_members;

    const save = el("button", "secondary", "Save");
    save.onclick = async () => {
      try {
        await api(`/api/admin/topics/${t.id}`, "PUT", {
          title: title.value,
          max_members: Number(size.value),
          active: !!t.active
        });
        await refresh();
      } catch (err) {
        message("topicMsg", err.message, true);
      }
    };

    const toggle = el(
      "button",
      "secondary",
      t.active ? "Deactivate" : "Activate"
    );

    toggle.onclick = async () => {
      try {
        await api(`/api/admin/topics/${t.id}`, "PUT", {
          title: title.value,
          max_members: Number(size.value),
          active: !t.active
        });
        await refresh();
      } catch (err) {
        message("topicMsg", err.message, true);
      }
    };

    form.append(title, size, save, toggle);
    row.append(form);

  

    const del = el("button", "secondary", "Delete");
    del.type = "button";

    del.onclick = async () => {
      const warning = t.booked
        ? `Delete booked topic "${t.title}" AND its registered group and members?`
        : `Delete topic "${t.title}"?`;

      if (!confirm(warning + " This cannot be undone.")) {
        return;
      }

      const admin_password = prompt(
        "Enter your ADMIN login password to confirm deletion:"
      );

      if (admin_password === null) return;

      try {
        await api(
          `/api/admin/topics/${t.id}`,
          "DELETE",
          { admin_password }
        );

        message("topicMsg", "Topic deleted successfully.");
        await refresh();
      } catch (err) {
        message("topicMsg", err.message, true);
      }
    };

    row.append(del);







    topicList.append(row);
  });

  const studentList = $("studentList");
  studentList.replaceChildren();

  students.forEach(st => {
    const row = el("div", "record");
    row.append(el("strong", "", `${st.name} (${st.usn})`));

    const controls = el("div", "actions");

    const pass = el("input");
    pass.type = "password";
    pass.placeholder = "Enter new password";
    pass.minLength = 8;
    pass.maxLength = 128;
    pass.autocomplete = "new-password";

    const show = el("button", "secondary", "Show");
    show.type = "button";

    show.onclick = () => {
      pass.type =
        pass.type === "password" ? "text" : "password";
      show.textContent =
        pass.type === "text" ? "Hide" : "Show";
    };

    const reset = el(
      "button",
      "secondary",
      "Reset Password"
    );
    reset.type = "button";

    reset.onclick = async () => {
      if (pass.value.length < 8 || pass.value.length > 128) {
        return message(
          "studentMsg",
          "Password must contain 8–128 characters.",
          true
        );
      }

      if (!confirm(`Reset password for ${st.usn}?`)) return;

      try {
        const password = pass.value;
        await api(
          `/api/admin/students/${st.id}/password`,
          "PUT",
          { password }
        );

        pass.value = "";
        message(
          "studentMsg",
          "Password updated successfully."
        );
        await refresh();
      } catch (err) {
        message("studentMsg", err.message, true);
      }
    };

    controls.append(pass, show, reset);
    row.append(controls);

    const passwordRow = el("div", "actions");

    const display = el(
      "span",
      "hint",
      st.password_available
        ? "Password: ••••••••"
        : "Password unavailable — reset once"
    );

    const view = el(
      "button",
      "secondary",
      "View Password"
    );
    view.type = "button";
    view.disabled = !st.password_available;

    let revealed = null;

    view.onclick = async () => {
      if (revealed !== null) {
        revealed = null;
        display.textContent = "Password: ••••••••";
        view.textContent = "View Password";
        return;
      }

      try {
        const result = await api(
          `/api/admin/students/${st.id}/credential`
        );
        revealed = result.password;
        display.textContent = `Password: ${revealed}`;
        view.textContent = "Hide Password";
      } catch (err) {
        message("studentMsg", err.message, true);
      }
    };

    const copy = el(
      "button",
      "secondary",
      "Copy Password"
    );
    copy.type = "button";
    copy.disabled = !st.password_available;

    copy.onclick = async () => {
      try {
        const result = await api(
          `/api/admin/students/${st.id}/credential`
        );

        await navigator.clipboard.writeText(
          result.password
        );

        message("studentMsg", "Password copied.");
      } catch (err) {
        message("studentMsg", err.message, true);
      }
    };

    passwordRow.append(display, view, copy);
    row.append(passwordRow);
    studentList.append(row);
  });

  const registrationList = $("registrationList");
  registrationList.replaceChildren();

  regs.forEach(r => {
    const row = el("div", "record");
    row.append(el("div", "record-title", r.title));

    row.append(
      el(
        "small",
        "",
        new Date(r.created_at).toLocaleString()
      )
    );

    r.members.forEach(m => {
      row.append(
        el("div", "", `${m.name} (${m.usn})`)
      );
    });

    registrationList.append(row);
  });
}

$("createStudent").onsubmit = async e => {
  e.preventDefault();

  try {
    const usn = $("studentUsn").value.trim();
    const password = $("studentPassword").value;

    await api("/api/admin/students", "POST", {
      name: $("studentName").value,
      usn,
      password
    });

    $("createStudent").reset();

    message(
      "studentMsg",
      "Student created. Password saved securely."
    );

    await refresh();
  } catch (err) {
    message("studentMsg", err.message, true);
  }
};

sessionCheck().catch(() => {
  message(
    "loginMsg",
    "Could not connect to server.",
    true
  );
});
