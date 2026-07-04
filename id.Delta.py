import os
import time

# --- [ 📊 ฐานข้อมูลจำลองจากภาพที่พี่ส่งมา ] ---


def check_password():
    # กำหนดรหัสผ่านที่ถูกต้อง
    correct_password = "123456"
    attempts = 3  # ให้โอกาสกรอกผิดได้ 3 ครั้ง
    
    while attempts > 0:
        clear_screen()
        print("="*50)
        print("          🔒 SYSTEM LOCK /ระบบรักษาความปลอดภัย 🔒          ")
        print("="*50)
        user_pass = input(f"🔑 กรุณากรอกรหัสผ่านเพื่อเข้าใช้งาน (เหลือโอกาส {attempts} ครั้ง): ")
        
        if user_pass == correct_password:
            print("\n✅ รหัสผ่านถูกต้อง! กำลังเข้าสู่ระบบ...")
            import time
            time.sleep(1.5)
            return True
        else:
            attempts -= 1
            print("\n❌ รหัสผ่านไม่ถูกต้อง!")
            import time
            time.sleep(1.5)
            
    print("\n🚨 คุณกรอกรหัสผิดเกินกำหนด ระบบจะปิดตัวลงอัตโนมัติ!")
    exit()

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def header():
    print("="*50)
    print("      🔍 ระบบสืบข้อมูลคนอื่นจากเบอร์และเลขบัตร 🔍")
    print("             (ไม่ได้มีข้อมูลทุกคนนะจ๊ะ ซื้อแล้วห้ามเปิดเผยนะจ๊ะ)")
    print("="*50)

def menu():
    while True:
        clear_screen()
        header()
        print("\n[ เมนู ]")
        print("1. เกี่ยวกับผู้สร้างสุดหล่อ")
        print("2. ใช้ค้นหาเสือกข้อมูลคนอื่น")
        print("3. ออกจากโปรแกรม")
        
        choice = input("\nกรุณาเลือกรายการ (1-3): ")

        if choice == '1':
            print("\n" + "-"*30)
            print("👤 ผู้สร้าง: สมไอซ์ บ้านเนิน")
            print("-"*30)
            input("\nกด Enter เพื่อกลับหน้าหลัก...")
        
        elif choice == '2':
            search_phone()
        
        elif choice == '3':
            print("\nปิดระบบ... ขอบคุณที่ใช้งาน!")
            break
        else:
            print("\n❌ เลือกไม่ถูก เอาใหม่ไอควาย!")
            time.sleep(1)

def search_phone():
    clear_screen()
    header()
    print("\n[ 🔎 ค้นหาข้อมูล ]")
    phone = input("กรุณากรอกเบอร์หรือเลขบัตรเป้าหมาย: ")
    
    print("\n⏳ กำลังค้นในระบบฐานข้อมูล... กรุณารอสักครู่")
    time.sleep(2) # ทำให้ดูสมจริงเหมือนกำลังแฮก

    if phone in DATABASE:
        data = DATABASE[phone]
        print("\n" + "✅ พบข้อมูลมันว่ะ!".center(50))
        print("-" * 50)
        print(f"📍 เบอร์-เลขบัตร : {phone}")
        print(f"👤 ชื่อ-นามสกุล  : {data['name']}")
        print(f"🆔 เลขบัตร ปชช. : {data['id_card']}")
        print(f"🏠 ที่อยู่ทะเบียน : {data['address']}")
        print(f"👨 ข้อมูลพ่อ     : {data['father']}")
        print(f"👩 ข้อมูลแม่     : {data['mother']}")
        print(f"📊 สถานะล่าสุด   : {data['status']}")
        print("-" * 50)
    else:
        print("\n❌ ไม่พบข้อมูล มึงแน่ใจว่าใส่ถูก")
    
    input("\nกด Enter เพื่อกลับหน้าหลัก...")

if __name__ == "__main__":
    # สั่งเช็กรหัสผ่านก่อนเป็นอันดับแรกสุด ถ้าผ่านค่อยไปหน้าเมนู
    check_password()
    menu()

if __name__ == "__main__":
    menu()
