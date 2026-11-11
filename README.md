# Student Topic Portal — no Group name

Student registration requires only a topic and member names/USNs. Admin registrations show topic and members.

## Update your existing project
1. **Back up `topics.db`** before replacing files. Do not delete the database.
2. Replace `app.py`, `templates/student.html`, `templates/admin.html`, `static/student.js`, `static/admin.js`, and `static/style.css` with the supplied files.
3. In Git Bash, set `export ADMIN_PASSWORD="YOUR_PRIVATE_PASSWORD"` if this is a fresh database, then run `python app.py`.
4. Refresh your browser using Ctrl+Shift+R.

The first startup migrates the old `registrations` table by dropping the unused `group_name` column while preserving the registrations and members. This needs SQLite 3.35+ (Python's bundled SQLite normally supports it).

No database file is included in this ZIP so existing student records are not overwritten.


## Student accounts

Students visit `/student/login` to create an account with their full name, USN, and a password (minimum 8 characters). They then sign in with USN and password. Student passwords are stored as hashes in the existing SQLite `topics.db`. Only signed-in students can submit a group registration. The signed-in student's name and USN are automatically included as Member 1 and cannot be changed on the form. The admin login remains separate at `/admin`.

For public deployment: set a persistent, unpredictable `SECRET_KEY`, enable HTTPS, use secure cookies (`SESSION_COOKIE_SECURE=True`), add login rate limiting and account verification or admin-issued credentials to prevent students claiming another person's USN. Self-registration does not verify USN ownership. Back up `topics.db` before upgrading.

## Public registered groups
Visit `/registered-groups` without logging in. This page lists booked topics, member names, and registration timestamps in Indian Standard Time. The API `/api/registered-groups` exposes only topic, member names, and date/time, not USNs or credentials. The list refreshes every 15 seconds.


## Admin-managed student accounts

Self-signup has been disabled. Only logged-in admins can create student accounts in **Admin Dashboard → Student accounts**, supplying full name, USN and initial password (minimum 8 characters). Admins can reset a student's password there. Students sign in at `/student/login` using credentials provided by the admin; forgotten passwords must be handled by the admin. No self-service password reset is available.

Existing `topics.db` is preserved. Do not overwrite it when upgrading. Passwords are stored as Werkzeug hashes. Resetting a password invalidates the student's existing session when it next accesses protected endpoints. Keep admin credentials secret, use HTTPS when deploying, and share student passwords privately.
