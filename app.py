import io
import requests
from flask import Flask, request, jsonify, send_from_directory
import mysql.connector
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__, static_folder='public', static_url_path='')

# إعدادات قاعدة البيانات MySQL
db_config = {
    'host': 'nozomi.proxy.rlwy.net',
    'user': 'root',
    'password': 'IfKQkXDNTONZBtEQCYWwWHTqDRdtSnbV',
    'database': 'railway',
    'port': 31645
}

# اتصال قاعدة البيانات
def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print("Database connection error:", err)
        return None

# خصائص الدواء القابلة للطلب
def get_medication_by_property(query):
    properties = {
        'الآثار الجانبية': 'side_effects',
        'الاستخدام': 'indication',
        'الجرعة': 'max_dose',
        'التكرار': 'frequency',
        'التفاعلات الدوائية': 'drug_interactions',
        'الحمل': 'pregnancy_safety',
        'الموانع': 'contraindications',
        'نوع': 'class'
    }
    for label, field in properties.items():
        if label in query:
            words = query.split()
            for word in words:
                if word not in label:
                    return word, field
    return None, None

# جلب خاصية محددة
def get_specific_property(med_name, field):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    sql = f"""
        SELECT {field} FROM medications
        WHERE LOWER(name) LIKE %s OR LOWER(generic_name) LIKE %s
    """
    like_pattern = f"%{med_name.lower()}%"
    cursor.execute(sql, (like_pattern, like_pattern))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[field] if result else None

# جلب كل أسماء الأدوية
def get_all_medications():
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name FROM medications")
    result = [row['name'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return result

# بحث دقيق
def get_exact_medication_info(query):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT * FROM medications
        WHERE LOWER(name) = LOWER(%s)
           OR LOWER(SUBSTRING_INDEX(name, ' ', 1)) = LOWER(%s)
    """
    cursor.execute(sql, (query, query))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

# بحث جزئي
def get_partial_medication_info(query):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    like = f"%{query.strip()}%"
    sql = """
        SELECT * FROM medications
        WHERE name LIKE %s OR generic_name LIKE %s
    """
    cursor.execute(sql, (like, like))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

# تنسيق معلومات الدواء
def format_medication_info(med):
    high_risk_str = "Yes" if med['high_risk'] in [1, True, "1"] else "No"
    hazard_str = "Yes" if med['hazard'] in [1, True, "1"] else "No"
    return (
        f"Name: {med['name']}\n"
        f"Generic: {med['generic_name']}\n"
        f"Class: {med['class']}\n"
        f"Indication: {med['indication']}\n"
        f"Frequency: {med['frequency']}\n"
        f"Max Dose: {med['max_dose']}\n"
        f"Contraindications: {med['contraindications']}\n"
        f"Drug Interactions: {med['drug_interactions']}\n"
        f"Pregnancy Safety: {med['pregnancy_safety']}\n"
        f"Side Effects: {med['side_effects']}\n"
        f"High Risk: {high_risk_str}\n"
        f"Hazard: {hazard_str}"
    )

# OpenAI فقط للتحية أو الأسئلة العامة
def get_answer_from_openai(query):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are Pharmexa, an assistant for pharmacists. If the user says hi or asks who you are, answer. For all other questions, say 'Sorry, I only answer drug-related questions from the database.'"},
                {"role": "user", "content": query}
            ]
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        print("OpenAI Error:", e)
        return "An error occurred."

# API endpoint
@app.route('/get-answer', methods=['POST'])
def get_answer():
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return jsonify({"error": "No query provided."}), 400

    # خاصية معينة
    med_name, field = get_medication_by_property(query)
    if med_name and field:
        value = get_specific_property(med_name, field)
        if value:
            return jsonify({"answer": f"{field.replace('_', ' ').capitalize()} for {med_name}: {value}"})

    # كل الأدوية
    if 'كل' in query or 'الأدوية' in query:
        meds = get_all_medications()
        return jsonify({"answer": "\n".join(meds)})

    # اسم دواء
    found = []
    for word in query.split():
        exact = get_exact_medication_info(word)
        if exact:
            found.extend(exact)
    if not found:
        for word in query.split():
            partial = get_partial_medication_info(word)
            if partial:
                found.extend(partial)
    unique = {med['name']: med for med in found}.values()
    if unique:
        meds = list(unique)
        if len(meds) == 1:
            return jsonify({"answer": format_medication_info(meds[0])})
        else:
            return jsonify({"answer": "\n\n".join([format_medication_info(m) for m in meds[:3]])})

    # سؤال عام أو تحية
    return jsonify({"answer": get_answer_from_openai(query)})

# صفحة HTML
@app.route('/')
def home():
    return send_from_directory('public', 'index.html')

if __name__ == "__main__":
    app.run(debug=True)
