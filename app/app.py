import streamlit as st
from streamlit_ace import st_ace

from problems import PROBLEMS
import judge
import db
import auth
import shutil
import subprocess


st.sidebar.write("iverilog:", shutil.which("iverilog"))
st.sidebar.write("vvp:", shutil.which("vvp"))

try:
    out = subprocess.run(
        ["iverilog", "-V"],
        capture_output=True,
        text=True,
    )
    st.sidebar.code(out.stdout)
except Exception as e:
    st.sidebar.error(str(e))
st.set_page_config(page_title="HDLCode", page_icon="🔧", layout="wide")
db.init_db()

PROBLEMS_BY_ID = {p["id"]: p for p in PROBLEMS}

# ---------------------------------------------------------------- session state
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None          # logged-in username, or None
if "must_change_password" not in st.session_state:
    st.session_state.must_change_password = False
if "current_problem" not in st.session_state:
    st.session_state.current_problem = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None


# ================================================================== AUTH GATE
def render_login_signup():
    st.title("🔧 HDLCode")
    st.caption("A LeetCode-style judge for Verilog / FSM design")

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            result = auth.login(username.strip(), password)
            if result["ok"]:
                st.session_state.auth_user = username.strip()
                st.session_state.must_change_password = result["must_change_password"]
                st.rerun()
            else:
                st.error(result["error"])

    with tab_signup:
        st.write(
            "Enter a username and your email. We'll email you a temporary password "
            "(your username plus 3 random digits) — you'll set your own on first login."
        )
        with st.form("signup_form"):
            new_username = st.text_input("Choose a username", key="signup_username")
            new_email = st.text_input("Email", key="signup_email")
            submitted = st.form_submit_button("Sign up", type="primary")
        if submitted:
            result = auth.signup(new_username.strip(), new_email.strip())
            if result["ok"]:
                if result["email_sent"]:
                    st.success(f"Account created! Check {new_email} for your temporary password.")
                else:
                    st.success("Account created!")
                    st.warning(
                        "No email server is configured on this deployment, so here is your "
                        "temporary password directly (this fallback is for local/dev use only "
                        "— see README to configure real email sending before going public):"
                    )
                    st.code(result["temp_password"])
            else:
                st.error(result["error"])


def render_force_password_change():
    st.title("🔧 HDLCode")
    st.warning("This is your first login with a temporary password. Please set your own password to continue.")
    with st.form("change_pw_form"):
        new_pw = st.text_input("New password", type="password")
        confirm_pw = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Set password", type="primary")
    if submitted:
        if new_pw != confirm_pw:
            st.error("Passwords don't match.")
        else:
            result = auth.change_password(st.session_state.auth_user, new_pw)
            if result["ok"]:
                st.session_state.must_change_password = False
                st.success("Password updated.")
                st.rerun()
            else:
                st.error(result["error"])


if st.session_state.auth_user is None:
    render_login_signup()
    st.stop()

if st.session_state.must_change_password:
    render_force_password_change()
    st.stop()

username = st.session_state.auth_user

# ================================================================== MAIN APP
with st.sidebar:
    st.title("🔧 HDLCode")
    st.caption(f"Logged in as **{username}**")

    if not judge.check_tools_available():
        st.error("Icarus Verilog (iverilog/vvp) not found on this machine. "
                  "See README for install instructions.")

    st.divider()
    st.subheader("Problems")
    solved_ids = db.get_solved_problem_ids(username)
    for p in PROBLEMS:
        solved = p["id"] in solved_ids
        label = f"{'✅ ' if solved else ''}{p['title']}"
        if st.button(label, key=f"nav_{p['id']}", use_container_width=True):
            st.session_state.current_problem = p["id"]
            st.session_state.last_result = None

    st.divider()
    if st.button("👤 My Profile", use_container_width=True):
        st.session_state.current_problem = "__profile__"
    if st.button("🏆 Leaderboard", use_container_width=True):
        st.session_state.current_problem = "__leaderboard__"

    st.divider()
    if st.button("Log out", use_container_width=True):
        st.session_state.auth_user = None
        st.session_state.current_problem = None
        st.rerun()


# ---------------------------------------------------------------- Profile page
if st.session_state.current_problem == "__profile__":
    st.header("👤 My Profile")
    stats = db.get_user_stats(username)
    user_row = db.get_user(username)

    col1, col2, col3 = st.columns(3)
    col1.metric("Problems solved", f"{stats['solved_count']} / {len(PROBLEMS)}")
    col2.metric("Total submissions", stats["submission_count"])
    col3.metric("Member since", user_row["created_at"][:10] if user_row else "—")

    st.divider()
    st.subheader("Account settings")

    with st.form("edit_username_form"):
        st.write("**Change username**")
        new_username = st.text_input("New username", value=username)
        submitted = st.form_submit_button("Update username")
    if submitted:
        new_username = new_username.strip()
        if new_username == username:
            st.info("That's already your username.")
        elif not auth.valid_username(new_username):
            st.error("Username must be 3-20 characters: letters, numbers, underscore only.")
        elif db.username_exists(new_username):
            st.error("That username is already taken.")
        else:
            db.rename_user(username, new_username)
            st.session_state.auth_user = new_username
            st.success(f"Username updated to {new_username}.")
            st.rerun()

    with st.form("change_password_form"):
        st.write("**Change password**")
        new_pw = st.text_input("New password", type="password", key="pw1")
        confirm_pw = st.text_input("Confirm new password", type="password", key="pw2")
        submitted_pw = st.form_submit_button("Update password")
    if submitted_pw:
        if new_pw != confirm_pw:
            st.error("Passwords don't match.")
        else:
            result = auth.change_password(username, new_pw)
            if result["ok"]:
                st.success("Password updated.")
            else:
                st.error(result["error"])

    st.divider()
    st.subheader("Recent submissions")
    rows = db.get_submission_history(username, limit=15)
    if not rows:
        st.info("No submissions yet — go solve something!")
    for row in rows:
        icon = "✅" if row["status"] == "PASS" else "❌"
        prob_title = PROBLEMS_BY_ID.get(row["problem_id"], {}).get("title", row["problem_id"])
        st.write(f"{icon} **{prob_title}** — `{row['status']}` — {row['created_at']}")

# ---------------------------------------------------------------- Leaderboard
elif st.session_state.current_problem == "__leaderboard__":
    st.header("🏆 Leaderboard")
    rows = db.get_leaderboard()
    if not rows:
        st.info("No one has solved a problem yet. Be the first!")
    else:
        for i, r in enumerate(rows, 1):
            st.write(f"**{i}. {r['username']}** — {r['solved_count']} solved")

# ---------------------------------------------------------------- Home
elif st.session_state.current_problem is None:
    st.header("Welcome to HDLCode 🔧")
    st.write(
        "Pick a problem from the sidebar. Each one is FSM-based, themed "
        "(superheroes, sports, banking, real-world hardware), and graded against a hidden "
        "testbench using real Icarus Verilog simulation."
    )
    cols = st.columns(2)
    for i, p in enumerate(PROBLEMS):
        with cols[i % 2]:
            with st.container(border=True):
                st.subheader(p["title"])
                st.caption(f"{p['theme']} · {p['difficulty']} · {p['skill']}")

# ---------------------------------------------------------------- Problem page
else:
    p = PROBLEMS_BY_ID[st.session_state.current_problem]

    st.header(p["title"])
    st.caption(f"**Theme:** {p['theme']}  |  **Difficulty:** {p['difficulty']}  |  **Tests:** {p['skill']}")

    tab_statement, tab_code, tab_history = st.tabs(["📄 Statement", "💻 Code", "📜 My Submissions"])

    with tab_statement:
        st.markdown(p["statement"])
        st.markdown("**Module interface (must match exactly):**")
        st.code(p["interface"], language="verilog")
        with st.expander("💡 Hints"):
            for h in p["hints"]:
                st.markdown(f"- {h}")

    with tab_code:
        editor_key = f"code_{p['id']}"
        if editor_key not in st.session_state:
            st.session_state[editor_key] = p["starter"]

        code = st_ace(
            value=st.session_state[editor_key],
            language="verilog",
            theme="tomorrow_night",
            key=f"ace_{p['id']}",
            height=420,
            font_size=14,
            tab_size=4,
            wrap=False,
            auto_update=True,
        )
        st.session_state[editor_key] = code

        col_run, col_submit, col_reset = st.columns([1, 1, 1])
        run_clicked = col_run.button("▶ Run / Submit", type="primary")
        reset_clicked = col_reset.button("↺ Reset to starter code")

        if reset_clicked:
            st.session_state[editor_key] = p["starter"]
            st.rerun()

        if run_clicked:
            with st.spinner("Compiling and simulating with Icarus Verilog..."):
                result = judge.run_submission(code, p["testbench"])
            db.record_submission(username, p["id"], result["status"], code)
            st.session_state.last_result = result

        if st.session_state.last_result:
            r = st.session_state.last_result
            if r["status"] == "PASS":
                st.success("✅ Accepted — all hidden tests passed.")
            elif r["status"] == "FAIL":
                st.error("❌ Wrong Answer — some hidden tests failed.")
            elif r["status"] == "COMPILE_ERROR":
                st.error("🛑 Compile Error")
            elif r["status"] == "TIMEOUT":
                st.error("⏱ Time Limit Exceeded")
            else:
                st.warning("⚠️ Judge Error")

            with st.expander("Simulator output", expanded=(r["status"] != "PASS")):
                st.code(r["raw_output"] or "(no output)", language="text")

    with tab_history:
        rows = db.get_submission_history(username, p["id"])
        if not rows:
            st.info("No submissions yet for this problem.")
        for row in rows:
            icon = "✅" if row["status"] == "PASS" else "❌"
            st.write(f"{icon} `{row['status']}` — {row['created_at']}")
