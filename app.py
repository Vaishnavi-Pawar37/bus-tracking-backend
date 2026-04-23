import random
import string
import base64
import os
import qrcode
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector

app = Flask(__name__)
# Enable CORS to allow the React frontend (port 3000) to communicate with this backend 
CORS(app)

# Database Configuration 
db_config = {
    'host': 'localhost',
    'user': 'root', 
    'password': 'Vaishnavi@123',
    'database': 'smart_bus_system' # Ensure this matches your MySQL exact database name
}

def get_db():
    """Establishes connection to the MySQL database"""
    return mysql.connector.connect(**db_config)

# Ensure required directories exist for images and QRs
if not os.path.exists('student_photos'): os.makedirs('student_photos')
if not os.path.exists('static/qrs'): os.makedirs('static/qrs')

# ==========================================================
# 1. NEW FRONTEND REGISTRATION ROUTE (React App Compatible)
# ==========================================================
@app.route('/register-student', methods=['POST'])
def register_student():
    data = request.json
    try:
        s_id = data.get('s_id')
        name = data.get('name')
        password = data.get('password')
        
        # FIX: Check multiple possible names sent from frontend so data is never lost
        mobile_no = data.get('mobile_no') or data.get('mobile') 
        route_id = data.get('route_id') or data.get('route') or data.get('stop')
        
        image_data = data.get('image')

        # Save Photo for Face Recognition
        if image_data:
            header, encoded = image_data.split(",", 1)
            binary_data = base64.b64decode(encoded)
            with open(f"student_photos/{s_id}.jpg", "wb") as f:
                f.write(binary_data)

        # Generate Unique QR Code
        qr_info = f"STU-{s_id}"
        qr_img = qrcode.make(qr_info)
        qr_img.save(f"static/qrs/{s_id}.png")

        # Store record in MySQL
        conn = get_db()
        cursor = conn.cursor()
        
        query = """
            INSERT INTO students (student_id, name, password, mobile_no, route_id, qr_code_data, fee_status) 
            VALUES (%s, %s, %s, %s, %s, %s, 'Not Paid')
        """
        cursor.execute(query, (s_id, name, password, mobile_no, route_id, qr_info))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Registration successful!"}), 201
    except Exception as e:
        print(f"Error in register-student: {e}")
        return jsonify({"error": str(e)}), 400

# ==========================================================
# 1.5 LEGACY REGISTRATION ROUTE (Kept for your Drivers)
# ==========================================================
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    role = data.get('role')
    name = data.get('name')
    username = data.get('username') 
    bus_no = data.get('bus_no')
    
    # FIX: Check multiple possible names sent from frontend
    mobile = data.get('mobile') or data.get('mobile_no')

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        if role == 'student':
            photo = data.get('photo')
            # FIX: Check multiple possible names sent from frontend
            stop = data.get('stop') or data.get('route_id') or data.get('route')
            
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            qr_data = f"STU-{random.randint(10000, 99999)}"
            
            cursor.execute("""
                INSERT INTO students (name, mobile_no, photo, username, password, bus_no, route_id, qr_code_data, fee_status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Not Paid')
            """, (name, mobile, photo, username, password, bus_no, stop, qr_data))
            conn.commit()
            
            return jsonify({"message": "Student registered successfully", "student_id": qr_data, "password": password}), 201
            
        elif role == 'driver':
            password = data.get('password')
            route = data.get('route') or data.get('route_id')
            license_no = data.get('license_no', 'PENDING')
            
            cursor.execute("""
                INSERT INTO drivers (name, username, password, license_no, bus_no, route_id) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, username, password, license_no, bus_no, route))
            conn.commit()
            
            return jsonify({"message": "Driver registered successfully"}), 201
            
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# ==========================================================
# 2. UNIFIED LOGIN ROUTE
# ==========================================================
@app.route('/login', methods=['POST'])
def login():
    """Handles login for Students, Drivers, and Admin"""
    data = request.json
    role = data.get('role')
    username = data.get('username') 
    password = data.get('password') 

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if role == 'admin':
        if username == 'admin' and password == 'admin123':
            return jsonify({"role": "admin", "name": "System Admin"}), 200
    
    elif role == 'student':
        # We also support login by student_id instead of username for React
        s_id = data.get('s_id')
        if s_id:
            cursor.execute("SELECT * FROM students WHERE student_id = %s AND password = %s", (s_id, password))
        else:
            cursor.execute("SELECT * FROM students WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        if user: 
            return jsonify({**user, "role": "student", "student": user}), 200

    elif role == 'driver':
        cursor.execute("SELECT * FROM drivers WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        if user: 
            return jsonify({**user, "role": "driver"}), 200

    cursor.close()
    conn.close()
    return jsonify({"error": "Invalid Credentials"}), 401


# ==========================================================
# 3. ADMIN DATA MANAGEMENT
# ==========================================================
@app.route('/admin/data', methods=['GET'])
def admin_data():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Get Students
    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()
    
    # 2. Get Drivers
    cursor.execute("SELECT * FROM drivers")
    drivers = cursor.fetchall()
    
    # 3. NEW: Get Location Pricing (Bus Info)
    cursor.execute("SELECT * FROM bus_info_pricing")
    bus_info = cursor.fetchall()
    
    # 4. NEW: Get Global Stats
    cursor.execute("SELECT * FROM bus_stats WHERE id=1")
    stats = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    # Send EVERYTHING to React so both AdminDashboard and BusInfo can see it!
    return jsonify({
        "students": students, 
        "drivers": drivers,
        "busInfo": bus_info,
        "stats": stats if stats else {} # Send empty object if stats table is empty
    })


@app.route('/admin/remove-student/<int:id>', methods=['DELETE'])
def remove_student(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE student_id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Student removed successfully"}), 200

@app.route('/admin/update-fee/<int:id>', methods=['PUT'])
@app.route('/update-fee', methods=['POST']) 
def update_fee(id=None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Support both PUT (path param) and POST (JSON body)
        if request.method == 'POST':
            id = request.json.get('s_id')
            new_status = request.json.get('status')
            cursor.execute("UPDATE students SET fee_status = %s WHERE student_id = %s", (new_status, id))
        else:
            cursor.execute("UPDATE students SET fee_status = 'Paid' WHERE student_id = %s", (id,))
        
        conn.commit()
        return jsonify({"message": "Fee status updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/students', methods=['GET'])
def get_students():
    """React Admin Dashboard support route"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(result)


# ==========================================================
# 4. DRIVER: VIEW ASSIGNED STUDENTS
# ==========================================================
@app.route('/driver/students/<bus_no>', methods=['GET'])
def driver_students(bus_no):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name, roll_no, fee_status FROM students WHERE bus_no = %s", (bus_no,))
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(students), 200

# ==========================================================
# 5. MOBILE QR SCANNER VERIFICATION 
# ==========================================================
@app.route('/api/verify-scan/<student_id>', methods=['GET'])
def verify_scan_api(student_id):
    """Fetches student data based on QR string (e.g. STU-1001)"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT name, photo, fee_status, qr_code_data, bus_no, route_id 
        FROM students 
        WHERE qr_code_data = %s
    """, (student_id,))
    
    student = cursor.fetchone()
    cursor.close()
    conn.close()

    if student:
        return jsonify(student), 200
    return jsonify({"error": "Student not found"}), 404

# ==========================================================
# 6. HARDWARE SCANNER ENTRY VERIFICATION
# ==========================================================
@app.route('/verify-entry', methods=['POST'])
def verify():
    data = request.json
    qr = data.get('qr_code_data')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM students WHERE qr_code_data = %s", (qr,))
    student = cursor.fetchone()
    
    if student and student['fee_status'] == 'Paid':
        cursor.execute("INSERT INTO attendance (student_id, bus_no) VALUES (%s, %s)", 
                       (student['student_id'], student['bus_no']))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "Success", "message": f"Welcome {student['name']}"}), 200
    
    cursor.close()
    conn.close()
    return jsonify({"status": "Rejected", "reason": "Fee Not Paid or Not Registered"}), 403

# ==========================================================
# 7. NEW: UPDATE STATS AND ADD/DELETE BUS INFO
# ==========================================================

# Route to Update the Global Stats
@app.route('/admin/update-stats', methods=['PUT', 'OPTIONS'])
def update_stats():
    if request.method == "OPTIONS":
        return jsonify({}), 200
        
    data = request.json
    
    # FIXED: Replaced 'db' with 'conn' and used 'get_db()'
    conn = get_db()
    cursor = conn.cursor() 
    try:
        cursor.execute('''
            UPDATE bus_stats 
            SET total_buses=%s, active_routes=%s, total_stops=%s, bus_nos=%s 
            WHERE id=1
        ''', (
            data.get('total_buses', 0), 
            data.get('active_routes', 0), 
            data.get('total_stops', 0), 
            data.get('bus_nos', '0')
        ))
        conn.commit() # FIXED
        return jsonify({"message": "Stats updated successfully"}), 200
    except Exception as e:
        print("Backend Error:", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close() # FIXED

# Route to Add a New Bus Stop/Asset
@app.route('/admin/add-bus-info', methods=['POST', 'OPTIONS'])
def add_bus_info():
    if request.method == "OPTIONS":
        return jsonify({}), 200
        
    data = request.json
    conn = get_db() # FIXED
    cursor = conn.cursor() 
    try:
        cursor.execute('''
            INSERT INTO bus_info_pricing (location, price, type) 
            VALUES (%s, %s, %s)
        ''', (
            data.get('location'), 
            data.get('price', 0), 
            data.get('type', 'Main City')
        ))
        conn.commit() # FIXED
        return jsonify({"message": "Asset added successfully"}), 201
    except Exception as e:
        print("Backend Error:", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close() # FIXED

# Route to Delete a Bus Stop
@app.route('/admin/delete-bus-info/<int:id>', methods=['DELETE', 'OPTIONS'])
def delete_bus_info(id):
    if request.method == "OPTIONS":
        return jsonify({}), 200
        
    conn = get_db() # FIXED
    cursor = conn.cursor() 
    try:
        cursor.execute('DELETE FROM bus_info_pricing WHERE id = %s', (id,))
        conn.commit() # FIXED
        return jsonify({"message": "Asset deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close() # FIXED

# ==========================================================
# 8. FORGOT & RESET PASSWORD ROUTES
# ==========================================================

# Step 1: Verify the user exists
@app.route('/verify-user-reset', methods=['POST', 'OPTIONS'])
def verify_user_reset():
    if request.method == "OPTIONS":
        return jsonify({}), 200
        
    data = request.json
    role = data.get('role')
    username = data.get('username')
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        if role == 'student':
            # FIX: Removed student_id (INT) to prevent MySQL Strict Mode crashes
            cursor.execute("""
                SELECT * FROM students 
                WHERE username = %s 
                OR qr_code_data = %s 
                OR roll_no = %s
            """, (username, username, username))
        elif role == 'driver':
            cursor.execute("SELECT * FROM drivers WHERE username = %s", (username,))
        else:
            return jsonify({"error": "Invalid role"}), 400
            
        user = cursor.fetchone()
        
        if user:
            return jsonify({"message": "Account verified"}), 200
        else:
            return jsonify({"error": "Account not found"}), 404
            
    except Exception as e:
        print("Backend Error (Verify):", str(e))
        return jsonify({"error": "Database error"}), 500
    finally:
        cursor.close()
        conn.close()

# Step 2: Actually update the password
@app.route('/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    if request.method == "OPTIONS":
        return jsonify({}), 200
        
    data = request.json
    role = data.get('role')
    username = data.get('username')
    new_password = data.get('new_password')
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if role == 'student':
            # FIX: Removed student_id (INT) to prevent MySQL Strict Mode crashes
            cursor.execute("""
                UPDATE students 
                SET password = %s 
                WHERE username = %s 
                OR qr_code_data = %s 
                OR roll_no = %s
            """, (new_password, username, username, username))
        elif role == 'driver':
            cursor.execute("UPDATE drivers SET password = %s WHERE username = %s", (new_password, username))
            
        conn.commit()
        return jsonify({"message": "Password updated successfully"}), 200
        
    except Exception as e:
        print("Backend Error (Reset):", str(e))
        return jsonify({"error": "Failed to update password"}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)