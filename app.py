from flask import Flask, render_template, request, redirect, session, jsonify
import mysql.connector
import json, random, smtplib
from email.message import EmailMessage
from datetime import datetime
from config import *
from flask import redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'your_secret_key'

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

@app.route('/', methods=['GET', 'POST'])
def login():
    session.clear()
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if not user:
            cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)", (name, email, password))
            conn.commit()
            user_id = cursor.lastrowid
        else:
            user_id = user[0]
        cursor.close()
        conn.close()

        session['user_id'] = user_id
        session['email'] = email
        session.pop('last_score', None)
        session.pop('last_total', None)
        session.pop('email_sent', None)
        session.pop('subject', None)
        session.pop('question_count', None)
        session.pop('questions', None)
        return redirect('/index')
    return render_template('login.html')

@app.route('/index', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        subject = request.form['subject']
        question_count = int(request.form['question_count'])
        time_limit = {10: 7, 20: 15, 30: 20}[question_count]
        session['subject'] = subject
        session['question_count'] = question_count
        session['time_limit'] = time_limit
        return redirect('/quiz')

    return render_template('index.html')

@app.route('/quiz')
def quiz():
    subject = session.get('subject')
    count = session.get('question_count')

    if not subject or not count:
        return redirect('/index')

    with open(f'questions/{subject.lower()}.json', encoding='utf-8') as f:
        all_questions = json.load(f)

    selected_questions = random.sample(all_questions, count)
    session['questions'] = selected_questions

    return render_template('quiz.html', questions=selected_questions, time=session['time_limit'])

def send_email(to_email, subject, correct, total_questions):
    sender_email = EMAIL_USER
    sender_password = EMAIL_PASSWORD  # Use app password if using Gmail with 2FA

    message = EmailMessage()
    message.set_content(f"Hello,\n\nYour result for the subject '{subject}':\nScore: {correct} out of {total_questions}\n\nThanks for taking the quiz!")

    message['Subject'] = f"Quiz Result: {subject}"
    message['From'] = sender_email
    message['To'] = to_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(message)
        print("Email sent successfully")
        return True
    except Exception as e:
        print("Email send failed:", e)
        return False
        
@app.route('/submit', methods=['POST'])
def submit():
    if 'questions' not in session or 'user_id' not in session:
        return jsonify({"error": "Session expired or invalid"}), 400

    data = request.get_json()
    answers = data['answers']
    correct = 0

    for i, q in enumerate(session['questions']):
        key = f"q{i}"  # Updated to match the frontend input names
        if q['answer'].strip() == answers.get(key, '').strip():
            correct += 1

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO results (user_id, subject, score, total_questions) VALUES (%s, %s, %s, %s)",
                   (session['user_id'], session['subject'], correct, session['question_count']))
    conn.commit()
    cursor.close()
    conn.close()


    try:
        send_email(session['email'], session['subject'], correct, session['question_count'])
        email_sent = True
    except Exception as e:
        print("Email send failed:", e)
        email_sent = False
    session['last_score'] = correct
    session['last_total'] = session['question_count']
    session['email_sent'] = email_sent

    return jsonify({"redirect": "/result"})


@app.route('/result')
def result():
    score = session.get('last_score')
    total = session.get('last_total')
    email = session.get('email')
    email_sent = session.get('email_sent')

    return render_template('result.html', score=score, total=total, email=email, email_sent=email_sent)

@app.route('/logout')
def logout():
    session.clear()  # Clears all session data
    return redirect(url_for('index'))  # Redirects to the home page

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


if __name__ == '__main__':
    app.run(debug=True)
