from flask import Flask, render_template, request, redirect, url_for, session as flask_session, send_file, Response
from datetime import datetime
import os
import pandas as pd
from io import BytesIO

from models import db, User, Student, SchoolClass, AttendanceSession, AttendanceRecord
from face_utils import gen_register_face, gen_attendance

app = Flask(__name__)
app.secret_key = "change_this_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:@localhost/attendance_db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True

db.init_app(app)

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

def setup_database():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            db.session.add(User(username="admin", password="admin", role="admin"))
            db.session.commit()

@app.route("/", methods=["GET", "POST"])
def login():
    if "user_id" in flask_session: return redirect(url_for("dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username"), password=request.form.get("password")).first()
        if user:
            flask_session["user_id"] = user.id
            flask_session["username"] = user.username
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    flask_session.clear()
    return redirect(url_for("login"))

def login_required():
    return "user_id" in flask_session

@app.route("/dashboard")
def dashboard():
    if not login_required(): return redirect(url_for("login"))
    return render_template("dashboard.html")

# NEW: Route to add new School Classes
@app.route("/add_class", methods=["POST"])
def add_class():
    if not login_required(): return redirect(url_for("login"))
    cname = request.form.get("class_name", "").strip()
    if cname and not SchoolClass.query.filter_by(class_name=cname).first():
        db.session.add(SchoolClass(class_name=cname))
        db.session.commit()
    return redirect(url_for("students"))

@app.route("/students", methods=["GET", "POST"])
def students():
    if not login_required(): return redirect(url_for("login"))
    if request.method == "POST":
        roll_no = request.form.get("roll_no", "").strip()
        name = request.form.get("name", "").strip()
        class_name = request.form.get("class_name", "").strip()
        if roll_no and name and class_name and not Student.query.filter_by(roll_no=roll_no).first():
            db.session.add(Student(roll_no=roll_no, name=name, class_name=class_name))
            db.session.commit()
        return redirect(url_for("students"))
    
    classes = SchoolClass.query.all()
    all_students = Student.query.all()
    return render_template("students.html", students=all_students, classes=classes)

# NEW: Returns HTML for popup window
@app.route("/register_popup/<int:student_id>")
def register_popup(student_id):
    if not login_required(): return redirect(url_for("login"))
    student = Student.query.get_or_404(student_id)
    return render_template("register_stream.html", student=student)

# NEW: Live video stream for registration
@app.route("/video_feed/register/<int:student_id>")
def video_feed_register(student_id):
    from flask import current_app
    return Response(gen_register_face(student_id, current_app._get_current_object()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/start_session", methods=["GET", "POST"])
def start_session():
    if not login_required(): return redirect(url_for("login"))
    if request.method == "POST":
        sess = AttendanceSession(
            class_name=request.form.get("class_name", "").strip(),
            subject=request.form.get("subject", "").strip(),
            faculty_name=flask_session.get("username", "Faculty"),
        )
        db.session.add(sess)
        db.session.commit()
        
        # Opens the popup using the newly created Session ID
        return render_template("attendance_stream.html", session_id=sess.id)
    
    classes = SchoolClass.query.all()
    return render_template("start_session.html", classes=classes)

# NEW: Live video stream for attendance
@app.route("/video_feed/attendance/<int:session_id>")
def video_feed_attendance(session_id):
    from flask import current_app
    return Response(gen_attendance(session_id, current_app._get_current_object()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# NEW: Ends the session when the popup closes
@app.route("/end_session/<int:session_id>")
def end_session(session_id):
    if not login_required(): return redirect(url_for("login"))
    sess = AttendanceSession.query.get(session_id)
    if sess:
        sess.end_time = datetime.utcnow().time()
        db.session.commit()
    return "Session Ended"

@app.route("/export/session/<int:session_id>")
def export_session_excel(session_id):
    if not login_required(): return redirect(url_for("login"))
    session_obj = AttendanceSession.query.get(session_id)
    if not session_obj: return "Session not found", 404
    records = AttendanceRecord.query.filter_by(session_id=session_id).all()
    students = {s.id: s for s in Student.query.all()}
    data = []
    for r in records:
        stu = students.get(r.student_id)
        if stu:
            data.append({
                "Session ID": session_obj.id, "Date": session_obj.date.strftime("%d-%m-%Y"),
                "Class": session_obj.class_name, "Subject": session_obj.subject,
                "Faculty": session_obj.faculty_name, "Student Name": stu.name,
                "Roll No": stu.roll_no, "Status": r.status,
                "Marked At": r.timestamp.strftime("%d-%m-%Y %H:%M:%S")
            })
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Attendance")
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"attendance_session_{session_id}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/attendance")
def view_attendance():
    if not login_required(): return redirect(url_for("login"))
    sessions = AttendanceSession.query.order_by(AttendanceSession.id.desc()).all()
    records = AttendanceRecord.query.all()
    students = {s.id: s for s in Student.query.all()}
    return render_template("view_attendance.html", sessions=sessions, records=records, students=students)

if __name__ == "__main__":
    setup_database()
    app.run(host="0.0.0.0", port=5000, debug=True)