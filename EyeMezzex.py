import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
import requests
import pyautogui
from PIL import ImageOps, Image
import psutil
import schedule
import time
import threading
import cloudinary
import cloudinary.uploader
import pytz
from datetime import datetime, timedelta
import socket
import urllib3
import keyboard
import logging
from win32com.client import Dispatch
from filelock import FileLock, Timeout
from timezonefinder import TimezoneFinder
import geopy
from geopy.geocoders import Nominatim

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Functions definitions
def is_another_instance_running(lock_file_path="app.lock"):
    lock = FileLock(lock_file_path)
    try:
        lock.acquire(timeout=1)
        return lock
    except Timeout:
        logging.debug("Another instance of the application is already running.")
        return None

def create_startup_task():
    try:
        startup_folder = os.path.join(os.getenv('AppData'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        shortcut_path = os.path.join(startup_folder, 'EyeMezzex.lnk')
        if not os.path.exists(startup_folder):
            os.makedirs(startup_folder)
        if not os.path.exists(shortcut_path):
            path = sys.argv[0]
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = path
            shortcut.WorkingDirectory = os.path.dirname(path)
            shortcut.save()
            logging.info(f"Shortcut created at {shortcut_path}")
        else:
            logging.info("Shortcut already exists.")
    except Exception as e:
        logging.error(f"Failed to create startup task: {e}")
        print(f"Error creating startup task: {e}")

# Global variables
TOKEN = None
USERNAME = None
USER_ID = None
STAFF_ID = None
TASKS = []
TASKTIMEID = None
STAFF_IN_TIME = None
RUNNING_TASKS = {}
ENDED_TASKS = []
TASK_ID_MAP = {}
SCREENSHOT_ENABLED = False
UPDATE_TASK_LIST_FLAG = False
BLOCKED_KEYS = ['win', 'alt', 'esc', 'ctrl']
blocked_keys_set = set()
staff_in_button_reference = None
staff_out_button_reference = None
task_counter = 0

# Function to get the latitude and longitude of the system's IP
def get_lat_long():
    try:
        response = requests.get('https://ipinfo.io/json')
        data = response.json()
        loc = data['loc'].split(',')
        return float(loc[0]), float(loc[1])
    except Exception as e:
        print(f"Error getting location: {e}")
        return None, None

# Function to get the timezone from latitude and longitude
def get_timezone(lat, long):
    tf = TimezoneFinder()
    return tf.timezone_at(lng=long, lat=lat)

# Get the latitude and longitude
latitude, longitude = get_lat_long()

# Get the local timezone based on latitude and longitude
if latitude and longitude:
    local_timezone = get_timezone(latitude, longitude)
else:
    local_timezone = 'UTC'

def main():
    root = ctk.CTk()
    def on_resize(event):
        global running_task_treeview_reference
        if 'running_task_treeview_reference' in globals():
            try:
                running_task_treeview_reference.resize()
            except tk.TclError:
                pass

    root.bind("<Configure>", on_resize)
    lock = is_another_instance_running()
    if not lock:
        sys.exit(0)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mezzex_logo.ico")

    # Cloudinary configuration
    cloudinary.config(
        cloud_name='du0vb79mg',
        api_key='653838984145584',
        api_secret='f3V5J_bW3d0pebFOkDtZDv697OU'
    )

    def block_input():
        global blocked_keys_set
        blocked_keys_set.clear()
        for key in BLOCKED_KEYS:
            keyboard.block_key(key)
            blocked_keys_set.add(key)

    def unblock_input():
        global blocked_keys_set
        for key in BLOCKED_KEYS:
            if key in blocked_keys_set:
                keyboard.unblock_key(key)
                blocked_keys_set.remove(key)

    def get_staff_in_time(user_id):
        url = f"https://smapi.mezzex.com/api/Data/getStaffInTime?userId={user_id}&clientTimeZone={local_timezone}"
        try:
            response = requests.get(url, verify=False)
            if response.status_code == 200:
                data = response.json()
                staff_in_time = datetime.fromisoformat(data['staffInTime'])
                staff_id = data['staffId']
                return staff_in_time, staff_id
            else:
                print(f"Failed to fetch staff in time: {response.status_code}, {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}")
        return None, None

    def login(email, password):
        url = "https://smapi.mezzex.com/api/AccountApi/login"
        data = {"Email": email, "Password": password}
        try:
            response = requests.post(url, json=data, verify=False)
            if response.status_code == 200:
                response_json = response.json()
                if response_json.get("message") == "Login successful":
                    global TOKEN, USERNAME, USER_ID, SCREENSHOT_ENABLED, STAFF_IN_TIME, STAFF_ID
                    TOKEN = response_json.get("token")
                    USERNAME = response_json.get("username")
                    USER_ID = response_json.get("userId")
                    SCREENSHOT_ENABLED = True
                    STAFF_IN_TIME, STAFF_ID = get_staff_in_time(USER_ID)
                    return USERNAME, USER_ID
        except requests.exceptions.RequestException:
            pass
        return None, None

    def fetch_tasks():
        url = "https://smapi.mezzex.com/api/Data/getTasks"
        try:
            response = requests.get(url, verify=False)
            if response.status_code == 200:
                tasks = response.json()
                TASK_ID_MAP.clear()
                task_names = {task['name'] for task in tasks}
                for task in tasks:
                    TASK_ID_MAP[task['name']] = task['id']
                return list(task_names)
        except requests.exceptions.RequestException:
            pass
        return []

    def start_task(task_type, task_type_entry, comment_entry):
        global TASKS, task_counter, STAFF_IN_TIME, STAFF_ID
        if STAFF_IN_TIME is None:
            staff_in()
            if STAFF_IN_TIME:
                staff_in_time_label_reference.configure(text=f"Staff In Time: {STAFF_IN_TIME.strftime('%H:%M:%S')}")
            else:
                messagebox.showerror("Error", "Unable to fetch Staff In Time.")
                return
        
        if any(task for task in RUNNING_TASKS.values() if task['staff_name'] == USERNAME):
            messagebox.showerror("Error", "You already have a running task. Please end the current task before starting a new one.")
            return
        
        if task_type == "Select Task Type":
            messagebox.showerror("Error", "Please select a task type.")
            return
        if task_type == "Other" and not comment_entry.get():
            messagebox.showerror("Error", "Comment cannot be empty for 'Other' task type.")
            return

        comment = comment_entry.get().strip()
        task_id = TASK_ID_MAP.get(task_type, 1)
        # Ensure start time is in IST
        task = {"task_type": task_type, "comment": comment, "start_time": datetime.now(), "task_id": task_id}
        TASKS.append(task)
        save_task(task)
        task_counter += 1
        start_task_record(task_counter, task)
        task_type_entry.delete(0, tk.END)
        comment_entry.delete(0, tk.END)
        update_task_list()

    def staff_in():
        global STAFF_IN_TIME
      
        # Fallback to current time in IST if API fails
        STAFF_IN_TIME = datetime.now(pytz.timezone(local_timezone))
        save_staff_in_time()

    def fetch_completed_tasks(user_id):
        url = f"https://smapi.mezzex.com/api/Data/getUserCompletedTasks?userId={user_id}&clientTimeZone={local_timezone}"
        try:
            response = requests.get(url, verify=False)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException:
            pass
        return []

    def take_screenshot():
        if not SCREENSHOT_ENABLED:
            return
        screenshot = pyautogui.screenshot()
        screenshot = ImageOps.exif_transpose(screenshot)
        image_url = upload_to_cloudinary(screenshot)
        if image_url:
            upload_data(image_url, get_system_info(), get_activity_log())

    def upload_to_cloudinary(screenshot):
        try:
            screenshot.save("screenshot_temp.jpg", "JPEG", quality=20, optimize=True)
            response = cloudinary.uploader.upload("screenshot_temp.jpg", upload_preset="ml_default")
            return response.get('url')
        except Exception:
            return None

    def get_system_info():
        system_info = psutil.virtual_memory()
        system_name = socket.gethostname()
        return f"System Info: {system_info}, System Name: {system_name}"

    def get_activity_log():
        return "Activity Log"

    def upload_data(image_url, system_info, activity_log):
        current_time = datetime.now(pytz.timezone(local_timezone)).isoformat()
        system_name = socket.gethostname()
        url = "https://smapi.mezzex.com/api/Data/saveScreenCaptureData"
        data = {
            "ImageUrl": image_url,
            "CreatedOn": current_time,
            "SystemName": system_name,
            "Username": USERNAME,
            "TaskTimerId": TASKTIMEID,
            "ClientTimeZone": local_timezone
        }
        try:
            requests.post(url, json=data, verify=False)
        except requests.exceptions.RequestException:
            pass

    def start_scheduled_tasks():
        schedule.every(5).minutes.do(take_screenshot)
        while True:
            schedule.run_pending()
            time.sleep(1)

    def on_login_click(event=None):
        global TOKEN, USERNAME, USER_ID
        email = username_entry.get()
        password = password_entry.get()
        USERNAME, USER_ID = login(email, password)
        if USERNAME:
            root.unbind_all("<KeyPress>")
            unblock_input()
            show_task_management_screen(USERNAME, USER_ID)
            threading.Thread(target=start_scheduled_tasks).start()
        else:
            messagebox.showerror("Login Failed", "Invalid email or password.")

    def show_task_management_screen(username, user_id):
        global UPDATE_TASK_LIST_FLAG, running_task_treeview_reference, ended_task_treeview_reference, current_time_label_reference, staff_in_time_label_reference, staff_in_button_reference, staff_out_button_reference
        UPDATE_TASK_LIST_FLAG = True
        for widget in root.winfo_children():
            widget.destroy()
        root.attributes('-fullscreen', False)

        top_row_frame = ctk.CTkFrame(root, fg_color="#2c3e50")
        top_row_frame.grid(row=0, column=0, columnspan=6, pady=10, sticky="ew")

        current_time_label = ctk.CTkLabel(top_row_frame, text="", font=("Helvetica", 14, "bold"), fg_color="#2c3e50", text_color="#ecf0f1")
        current_time_label.grid(row=0, column=0, sticky="w", padx=10)
        current_time_label_reference = current_time_label
        update_current_time()

        welcome_label = ctk.CTkLabel(top_row_frame, text=f"Welcome, {username}!", font=("Helvetica", 18, "bold"), fg_color="#2c3e50", text_color="#ecf0f1")
        welcome_label.grid(row=0, column=1, sticky="ew")    
        refresh_button = ctk.CTkButton(top_row_frame, text="Refresh", fg_color="#2980b9", text_color="#ecf0f1", font=("Helvetica", 14, "bold"), command=refresh_ui, height=30, width=100)
        refresh_button.grid(row=0, column=2, sticky="e", padx=10)

        top_row_frame.grid_columnconfigure(0, weight=1)
        top_row_frame.grid_columnconfigure(1, weight=3)
        top_row_frame.grid_columnconfigure(2, weight=1)

        staff_buttons_frame = ctk.CTkFrame(root, fg_color="#2c3e50")
        staff_buttons_frame.grid(row=1, column=0, columnspan=6, pady=10, sticky="ew")

        staff_in_button = ctk.CTkButton(staff_buttons_frame, text="Staff In", fg_color="#3498db", text_color="#ecf0f1", font=("Helvetica", 12), command=staff_in, height=30, width=100)
        staff_in_button.pack(side="left", padx=12)
        staff_out_button = ctk.CTkButton(staff_buttons_frame, text="Staff Out", fg_color="#e74c3c", text_color="#ecf0f1", font=("Helvetica", 12), command=staff_out, height=30, width=100)
        staff_out_button.pack(side="left", padx=12)

        if STAFF_IN_TIME is None:
            staff_in_button.configure(state=tk.NORMAL)
            staff_out_button.configure(state=tk.DISABLED)
        else:
            staff_in_button.configure(state=tk.DISABLED)
            staff_out_button.configure(state=tk.NORMAL)

        staff_in_time_label = ctk.CTkLabel(staff_buttons_frame, text=f"Staff In Time: {STAFF_IN_TIME.strftime('%H:%M:%S') if STAFF_IN_TIME else 'Not Logged In'}", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12, "bold"))
        staff_in_time_label.pack(side="left", padx=12)

        staff_in_button_reference = staff_in_button
        staff_out_button_reference = staff_out_button
        staff_in_time_label_reference = staff_in_time_label

        tasks = fetch_tasks()
        task_names = tasks

        ctk.CTkLabel(root, text="Task Type:", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12, "bold")).grid(row=2, column=0, padx=10, pady=10, sticky="w")

        task_type_combobox = ctk.CTkComboBox(root, values=task_names, font=("Helvetica", 12), width=250, height=30, state="readonly")
        task_type_combobox.grid(row=2, column=1, padx=2, pady=10, sticky="ew")

        # Bind the click event to the combobox to open the dropdown
        task_type_combobox.bind("<Button-1>", lambda event: task_type_combobox.event_generate('<Down>'))

        task_type_combobox.bind("<<ComboboxSelected>>", lambda event: on_task_selected(task_type_combobox, task_type_entry))
        task_type_combobox.set("Select Task Type")

        task_type_entry = ctk.CTkEntry(root, font=("Helvetica", 12), width=250, height=30)
        task_type_entry.grid(row=2, column=2, padx=2, pady=10, sticky="ew")
        task_type_entry.grid_remove()


        ctk.CTkLabel(root, text="Comment:", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12, "bold")).grid(row=2, column=3, padx=10, pady=10, sticky="w")
        comment_entry = ctk.CTkEntry(root, font=("Helvetica", 12), width=200, height=30)
        comment_entry.grid(row=2, column=4, padx=2, pady=10, sticky="ew")

        start_task_button = ctk.CTkButton(root, text="Start Task", fg_color="#27ae60", text_color="#ecf0f1", font=("Helvetica", 12), command=lambda: start_task(task_type_combobox.get(), task_type_entry, comment_entry), height=30, width=100)
        start_task_button.grid(row=2, column=5, padx=10, pady=10, sticky="ew")

        root.bind("<Return>", lambda event: start_task(task_type_combobox.get(), task_type_entry, comment_entry))

        ctk.CTkLabel(root, text="Running Tasks", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12)).grid(row=3, column=0, columnspan=6, pady=5, padx=10, sticky="w")

        running_task_list_frame = tk.Frame(root, bg="#ecf0f1")
        running_task_list_frame.grid(row=4, column=0, columnspan=6, padx=10, pady=5, sticky="nsew")

        running_task_treeview = CustomTreeview(running_task_list_frame, columns=("Staff Name", "Task Type", "Comment", "Start Time", "Working Time", "End Task"), show="headings", selectmode="none")
        running_task_treeview.pack(expand=True, fill="both")

        for col in running_task_treeview["columns"]:
            running_task_treeview.heading(col, text=col, anchor="w")
            running_task_treeview.column(col, anchor="w")

        running_task_treeview_reference = running_task_treeview

        ctk.CTkLabel(root, text="Ended Tasks", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12)).grid(row=5, column=0, columnspan=6, pady=5, padx=10, sticky="w")

        ended_task_list_frame = tk.Frame(root, bg="#ecf0f1")
        ended_task_list_frame.grid(row=6, column=0, columnspan=6, padx=10, pady=5, sticky="nsew")

        ended_task_treeview = CustomTreeview(ended_task_list_frame, columns=("Staff Name", "Task Type", "Comment", "Start Time", "End Time", "Working Time"), show="headings", selectmode="none")
        ended_task_treeview.pack(expand=True, fill="both")

        for col in ended_task_treeview["columns"]:
            ended_task_treeview.heading(col, text=col, anchor="w")
            ended_task_treeview.column(col, anchor="w")

        ended_task_treeview_reference = ended_task_treeview

        update_task_list()

        for i in range(7):
            root.grid_rowconfigure(i, weight=0)
            root.grid_rowconfigure(4, weight=1)
            root.grid_rowconfigure(6, weight=1)
        for i in range(6):
            root.grid_columnconfigure(i, weight=1)

    def on_task_selected(task_type_combobox, task_type_entry):
        selected_task = task_type_combobox.get()
        task_type_entry.grid() if selected_task == "Other" else task_type_entry.grid_remove()
    
    def save_task(task):
        url = "https://smapi.mezzex.com/api/Data/saveTaskTimer"
        data = {
            "UserId": USER_ID,
            "TaskId": task["task_id"],
            "TaskComment": task["comment"],
            "taskStartTime": task["start_time"].isoformat(),
            "taskEndTime": None,
            "ClientTimeZone": local_timezone
        }
        try:
            response = requests.post(url, json=data, verify=False)
            if response.status_code == 200:
                response_json = response.json()
                if response_json.get("message") == "Task timer data uploaded successfully":
                    global TASKTIMEID
                    TASKTIMEID = response_json.get("taskTimeId")
        except requests.exceptions.RequestException:
            pass

    def save_staff_in_time():
        global STAFF_IN_TIME, STAFF_ID, SCREENSHOT_ENABLED
        STAFF_IN_TIME = datetime.now(pytz.timezone(local_timezone))
        SCREENSHOT_ENABLED = True
        data = {
            "staffInTime": STAFF_IN_TIME.isoformat(),
            "staffOutTime": None,
            "UserId": USER_ID,
            "ClientTimeZone": local_timezone
        }
        url = "https://smapi.mezzex.com/api/Data/saveStaff"
        try:
            response = requests.post(url, json=data, verify=False)
            if response.status_code == 200:
                response_json = response.json()
                if response_json.get("message") == "Staff data saved successfully":
                    STAFF_ID = response_json.get("staffId")
                    staff_in_time_label_reference.configure(text=f"Staff In Time: {STAFF_IN_TIME.strftime('%H:%M:%S')}")
                    staff_in_button_reference.configure(state=tk.DISABLED)
        except requests.exceptions.RequestException:
            pass

    def update_staff_out_time():
        global STAFF_ID, SCREENSHOT_ENABLED
        if STAFF_IN_TIME is None or STAFF_ID is None:
            return

        SCREENSHOT_ENABLED = False
        staff_out_time = datetime.now(pytz.timezone(local_timezone))
        data = {
            "staffInTime": STAFF_IN_TIME.isoformat(),
            "staffOutTime": staff_out_time.isoformat(),
            "UserId": USER_ID,
            "Id": STAFF_ID,
            "ClientTimeZone": local_timezone
        }
        url = "https://smapi.mezzex.com/api/Data/updateStaff"
        try:
            requests.post(url, json=data, verify=False)
        except requests.exceptions.RequestException:
            pass

    def start_task_record(task_counter, task):
        task_id = task_counter
        start_time = task["start_time"].strftime("%Y-%m-%dT%H:%M:%S")
        RUNNING_TASKS[task_id] = {
            "id": task_id,
            "staff_name": USERNAME,
            "task_type": task["task_type"],
            "comment": task["comment"],
            "start_time": start_time,
            "working_time": "00:00:00"
        }

    def end_task(task_id):
        task = RUNNING_TASKS.pop(int(task_id), None)
        if not task:
            print("Task not found.")
            return

        if task["staff_name"] != USERNAME:
            messagebox.showerror("Permission Denied", "You cannot end another user's task.")
            return

        # Ensure end time is in IST
        task["end_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        start_time = datetime.fromisoformat(task["start_time"])
        end_time = datetime.fromisoformat(task["end_time"])
        task["working_time"] = str(end_time - start_time).split(".")[0]
        ENDED_TASKS.append(task)

        global TASKTIMEID
        if TASKTIMEID is None:
            TASKTIMEID = fetch_task_time_id(task_id)
            if TASKTIMEID is None:
                print("Error: Unable to fetch valid TASKTIMEID.")
                return

        update_task_timer(task)

    def fetch_task_time_id(task_id):
        url = f"https://smapi.mezzex.com/api/Data/getTaskTimeId?taskId={task_id}&clientTimeZone={local_timezone}"
        try:
            response = requests.get(url, verify=False)
            if response.status_code == 200:
                data = response.json()
                return data.get('taskTimeId')
        except requests.exceptions.RequestException as e:
            print(f"Error fetching TASKTIMEID: {e}")
        return None

    def update_task_timer(task):
        if not isinstance(TASKTIMEID, int):
            print("Error: Invalid TASKTIMEID. TASKTIMEID should be a non-null integer.")
            return

        url = "https://smapi.mezzex.com/api/Data/updateTaskTimer"
        data = {
            "id": TASKTIMEID,
            "taskEndTime": task["end_time"],
            "ClientTimeZone": local_timezone
        }
        try:
            response = requests.post(url, json=data, verify=False)
            # refresh_ui()
            if response.status_code != 200:
                print(f"Failed to update task end time: {response.status_code}, response: {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}")

    def end_all_running_tasks():
        for task_id in list(RUNNING_TASKS.keys()):
            if RUNNING_TASKS[task_id]["staff_name"] == USERNAME:
                end_task(task_id)

    def ensure_end_task_buttons():
        for task_id, task in RUNNING_TASKS.items():
            if not running_task_treeview_reference.exists(str(task_id)):
                start_time = datetime.fromisoformat(task["start_time"])
                running_task_treeview_reference.insert(
                    "",
                    "end",
                    iid=str(task_id),
                    values=(
                        task["staff_name"],
                        task["task_type"],
                        task["comment"],
                        start_time.strftime("%H:%M:%S"),
                        task["working_time"],
                        ""
                    ),
                    tags=("end_task",)
                )
            running_task_treeview_reference.add_button(str(task_id))

    def fetch_task_timers(user_id):
        url = f"https://smapi.mezzex.com/api/Data/getTaskTimers?userId={user_id}&clientTimeZone={local_timezone}"
        try:
            response = requests.get(url, verify=False)
            if response.status_code == 200:
                task_timers = response.json()
                RUNNING_TASKS.clear()
                for task in task_timers:
                    if 'id' in task and isinstance(task['id'], int):
                        task_id = task['id']
                        RUNNING_TASKS[task_id] = {
                            "id": task_id,
                            "staff_name": task.get("userName", "Unknown"),
                            "task_type": task.get("taskName", "Unknown"),
                            "comment": task.get("taskComment", ""),
                            "start_time": datetime.fromisoformat(task['taskStartTime']).strftime('%Y-%m-%dT%H:%M:%S'),
                            "working_time": '00:00:00'
                        }
                ensure_end_task_buttons()
                return task_timers
        except requests.exceptions.RequestException as e:
            print(f"Error fetching task timers: {e}")
        return []

    def format_working_time(working_time_str):
        time_parts = working_time_str.split(':')
        days = 0
        if 'day' in time_parts[0]:
            days_part, time_part = time_parts[0].split(', ')
            days = int(days_part.split()[0])
            time_parts[0] = time_part

        hours, minutes, seconds = (0, 0, 0)
        try:
            if len(time_parts) == 3:
                hours, minutes, seconds = int(time_parts[0]), int(time_parts[1]), int(float(time_parts[2]))
            elif len(time_parts) == 2:
                minutes, seconds = int(time_parts[0]), int(float(time_parts[1]))
            elif len(time_parts) == 1:
                seconds = int(float(time_parts[0]))

            if days < 0:
                total_seconds = timedelta(hours=hours, minutes=minutes, seconds=seconds).total_seconds() + timedelta(hours=5, minutes=30).total_seconds()
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                hours, minutes, seconds = int(hours), int(minutes), int(seconds)
            else:
                hours += days * 24

            parts = []
            if hours != 0:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes != 0:
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            elif minutes == 0 and hours == 0:
                parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

            return ' '.join(parts)
        except ValueError:
            return "Invalid time format"
    
    def fetch_and_update_tasks():
        global RUNNING_TASKS, ENDED_TASKS

        task_timers = fetch_task_timers(USER_ID)
        running_tasks = {}
        for task in task_timers:
            task_id = task.get("id")
            if task_id:
                running_tasks[task_id] = {
                    "staff_name": task.get("userName", "Unknown"),
                    "task_type": task.get("taskName", "Unknown"),
                    "comment": task.get("taskComment", ""),
                    "start_time": datetime.fromisoformat(task.get("taskStartTime")).strftime('%Y-%m-%dT%H:%M:%S'),
                    "working_time": '00:00:00'
                }
        RUNNING_TASKS = running_tasks

        completed_tasks = fetch_completed_tasks(USER_ID)
        ended_tasks = []
        for task in completed_tasks:
            ended_task = {
                "staff_name": task.get("userName", "Unknown"),
                "task_type": task.get("taskName", "Unknown"),
                "comment": task.get("taskComment", ""),
                "start_time": datetime.fromisoformat(task.get("taskStartTime")).strftime("%Y-%m-%dT%H:%M:%S"),
                "end_time": datetime.fromisoformat(task.get("taskEndTime")).strftime("%Y-%m-%dT%H:%M:%S"),
                "working_time": str(datetime.fromisoformat(task.get("taskEndTime")) - datetime.fromisoformat(task.get("taskStartTime")))
            }
            ended_tasks.append(ended_task)
        ENDED_TASKS = ended_tasks

    def update_ui():
        if running_task_treeview_reference and running_task_treeview_reference.winfo_exists():
            existing_ids = set(running_task_treeview_reference.get_children())
            new_ids = set(str(task_id) for task_id in RUNNING_TASKS)
            for item_id in existing_ids - new_ids:
                running_task_treeview_reference.delete(item_id)

            items_to_reinsert = []
            for task_id, task in RUNNING_TASKS.items():
                task_id_str = str(task_id)
                start_time = datetime.fromisoformat(task["start_time"])
                start_time = pytz.timezone(local_timezone).localize(start_time)
                current_time_ist = datetime.now(pytz.timezone(local_timezone))
                working_time = str(current_time_ist - start_time).split(".")[0]
                task_data = (task["staff_name"], task["task_type"], task["comment"], start_time.strftime("%H:%M:%S"), working_time, "")
                is_current_user_task = task["staff_name"] == USERNAME
                tags = ("end_task", "current_user") if is_current_user_task else ("end_task",)

                if task_id_str in existing_ids:
                    if running_task_treeview_reference.item(task_id_str, 'values') != task_data:
                        running_task_treeview_reference.item(task_id_str, values=task_data)
                else:
                    running_task_treeview_reference.insert("", "end", iid=task_id_str, values=task_data, tags=tags)

                items_to_reinsert.append((task_id_str, task_data, tags, is_current_user_task))

            for item_id, _, _, _ in items_to_reinsert:
                running_task_treeview_reference.delete(item_id)

            for item_id, task_data, tags, is_current_user_task in sorted(items_to_reinsert, key=lambda x: not x[3]):
                running_task_treeview_reference.insert("", "end", iid=item_id, values=task_data, tags=tags)

        if ended_task_treeview_reference and ended_task_treeview_reference.winfo_exists():
            existing_ended_ids = set(ended_task_treeview_reference.get_children())
            new_ended_ids = set(f"{task['staff_name']}_{task['start_time']}" for task in ENDED_TASKS)

            for item_id in existing_ended_ids - new_ended_ids:
                ended_task_treeview_reference.delete(item_id)

            for task in ENDED_TASKS:
                start_time = datetime.fromisoformat(task["start_time"])
                end_time = datetime.fromisoformat(task["end_time"])
                start_time = pytz.timezone(local_timezone).localize(start_time)
                end_time = pytz.timezone(local_timezone).localize(end_time)
                working_time = format_working_time(task["working_time"])
                task_data = (task["staff_name"], task["task_type"], task["comment"], start_time.strftime("%H:%M:%S"), end_time.strftime("%H:%M:%S"), working_time)

                item_id = f"{task['staff_name']}_{task['start_time']}"
                if item_id in existing_ended_ids:
                    if ended_task_treeview_reference.item(item_id, 'values') != task_data:
                        ended_task_treeview_reference.item(item_id, values=task_data)
                else:
                    ended_task_treeview_reference.insert("", "end", iid=item_id, values=task_data)

        if root and root.winfo_exists():
            root.after(1000, update_ui)

    def update_task_list():
        if not UPDATE_TASK_LIST_FLAG:
            return
        
        fetch_and_update_tasks()
        update_ui()
        # root.after(60000, update_task_list)

    def staff_in():
        global STAFF_IN_TIME, staff_in_button_reference, staff_out_button_reference, staff_in_time_label_reference
        STAFF_IN_TIME = datetime.now(pytz.timezone(local_timezone))
        
        save_staff_in_time()
        
        if STAFF_IN_TIME is not None:
            staff_in_button_reference.configure(state=tk.DISABLED)
            staff_out_button_reference.configure(state=tk.NORMAL)
            staff_in_time_label_reference.configure(text=f"Staff In Time: {STAFF_IN_TIME.strftime('%H:%M:%S')}")
        else:
            staff_in_button_reference.configure(state=tk.NORMAL)
            staff_out_button_reference.configure(state=tk.DISABLED)

    def staff_out():
        update_staff_out_time()
        end_all_running_tasks()
        staff_in_button_reference.configure(state=tk.NORMAL)
        show_login_screen()

    def show_login_screen():
        global UPDATE_TASK_LIST_FLAG, username_entry, password_entry, show_password_var, RUNNING_TASKS, ENDED_TASKS
        UPDATE_TASK_LIST_FLAG = False
        
        RUNNING_TASKS.clear()
        ENDED_TASKS.clear()
        
        for widget in root.winfo_children():
            widget.destroy()
        root.attributes('-fullscreen', True)
        block_input()
        login_frame = ctk.CTkFrame(root, fg_color="#2c3e50", corner_radius=15)
        login_frame.pack(expand=True)

        login_title = ctk.CTkLabel(login_frame, text="Mezzex Eye", font=("Helvetica", 24, "bold"), fg_color="#2c3e50", text_color="#ecf0f1", pady=20)
        login_title.grid(row=0, column=0, columnspan=3, pady=(20, 10), padx=10, sticky="n")

        username_label = ctk.CTkLabel(login_frame, text="Username:", font=("Helvetica", 14), fg_color="#2c3e50", text_color="#ecf0f1", padx=10, pady=5)
        username_label.grid(row=1, column=0, pady=10, sticky="e")
        username_entry = ctk.CTkEntry(login_frame, font=("Helvetica", 14), width=300)
        username_entry.grid(row=1, column=1, pady=10, padx=(0, 10), sticky="w")

        password_label = ctk.CTkLabel(login_frame, text="Password:", font=("Helvetica", 14), fg_color="#2c3e50", text_color="#ecf0f1", padx=10, pady=5)
        password_label.grid(row=2, column=0, pady=10, sticky="e")
        password_entry = ctk.CTkEntry(login_frame, font=("Helvetica", 14), show="*", width=300)
        password_entry.grid(row=2, column=1, pady=10, padx=(0, 10), sticky="w")

        show_password_var = tk.BooleanVar()
        show_password_checkbutton = ctk.CTkCheckBox(login_frame, text="Show", variable=show_password_var, command=toggle_password_visibility)
        show_password_checkbutton.grid(row=2, column=2, padx=(10, 0), sticky="w")

        login_button = ctk.CTkButton(login_frame, text="Login", font=("Helvetica", 14), fg_color="#3498db", text_color="#ecf0f1", hover_color="#2980b9", command=on_login_click, width=100, height=30)
        login_button.grid(row=3, column=0, columnspan=3, pady=20)

        system_control_label = ctk.CTkLabel(login_frame, text="System Control", font=("Helvetica", 16, "bold"), fg_color="#2c3e50", text_color="#ecf0f1")
        system_control_label.grid(row=4, column=0, columnspan=3, pady=(10, 5), sticky="n")

        shutdown_button = ctk.CTkButton(login_frame, text="Shutdown", font=("Helvetica", 14), fg_color="#e74c3c", text_color="#ecf0f1", hover_color="#c0392b", command=shutdown, width=120, height=40)
        shutdown_button.grid(row=5, column=0, pady=10, padx=20, sticky="e")

        restart_button = ctk.CTkButton(login_frame, text="Restart", font=("Helvetica", 14), fg_color="#f39c12", text_color="#ecf0f1", hover_color="#e67e22", command=restart, width=120, height=40)
        restart_button.grid(row=5, column=2, pady=10, padx=20, sticky="w")

        root.bind("<Return>", on_login_click)

        login_frame.grid_rowconfigure(0, weight=1)
        login_frame.grid_rowconfigure(1, weight=1)
        login_frame.grid_rowconfigure(2, weight=1)
        login_frame.grid_rowconfigure(3, weight=1)
        login_frame.grid_rowconfigure(4, weight=1)
        login_frame.grid_rowconfigure(5, weight=1)
        login_frame.grid_columnconfigure(0, weight=1)
        login_frame.grid_columnconfigure(1, weight=1)
        login_frame.grid_columnconfigure(2, weight=1)

    def shutdown():
        os.system("shutdown /s /t 1")

    def restart():
        os.system("shutdown /r /t 1")

    def toggle_password_visibility():
        password_entry.configure(show="" if show_password_var.get() else "*")
        
    def refresh_ui():
        global USER_ID, running_task_treeview_reference, ended_task_treeview_reference, RUNNING_TASKS, ENDED_TASKS
        RUNNING_TASKS.clear()
        ENDED_TASKS.clear()
        tasks = fetch_tasks()
        completed_tasks = fetch_completed_tasks(USER_ID)
        task_timers = fetch_task_timers(USER_ID)

        for task in task_timers:
            task_id = task.get("id")
            if task_id:
                RUNNING_TASKS[task_id] = {
                    "staff_name": task.get("userName", "Unknown"),
                    "task_type": task.get("taskName", "Unknown"),
                    "comment": task.get("taskComment", ""),
                    "start_time": datetime.fromisoformat(task.get("taskStartTime")).strftime("%Y-%m-%dT%H:%M:%S"),
                    "working_time": "00:00:00"
                }

        for task in completed_tasks:
            ended_task = {
                "staff_name": task.get("userName", "Unknown"),
                "task_type": task.get("taskName", "Unknown"),
                "comment": task.get("taskComment", ""),
                "start_time": datetime.fromisoformat(task.get("taskStartTime")).strftime("%Y-%m-%dT%H:%M:%S"),
                "end_time": datetime.fromisoformat(task.get("taskEndTime")).strftime("%Y-%m-%dT%H:%M:%S"),
                "working_time": str(datetime.fromisoformat(task.get("taskEndTime")) - datetime.fromisoformat(task.get("taskStartTime")))
            }
            ENDED_TASKS.append(ended_task)

        update_task_list()
        print("Refreshed UI")
    class CustomTreeview(ttk.Treeview):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            self.style = ttk.Style()
            self.style.configure("Treeview", font=("Helvetica", 12), rowheight=32)
            self.style.configure("Treeview.Heading", font=("Helvetica", 14, "bold"), padding=(0, 0, 0, 10))
            self.buttons = {}

        def insert(self, parent, index, iid=None, **kw):
            item = super().insert(parent, index, iid=iid, **kw)
            if 'tags' in kw and 'end_task' in kw['tags']:
                self.add_button(item)
            # Add a separator after each task
            separator_id = super().insert("", "end", values=("",), tags=("separator",))
            self.tag_configure("separator", background="#e0e0e0")
            return item

        def add_button(self, item):
            if item not in self.buttons:
                btn = ttk.Button(self, text="End Task", command=lambda: self.end_task_callback(item))
                self.buttons[item] = btn
                self.place_button(item)

        def place_button(self, item, retry_count=0):
            if item in self.buttons:
                btn = self.buttons[item]
                bbox = self.bbox(item, column="#6")
                if bbox:
                    btn.place(x=bbox[0] + 2, y=bbox[1] + 2)
                else:
                    if retry_count < 5:  # Retry a few times
                        self.after(100, lambda: self.place_button(item, retry_count + 1))

        def end_task_callback(self, item):
            task_id = item
            task = RUNNING_TASKS.get(int(task_id))
            if task and task["staff_name"] == USERNAME:
                end_task(task_id)
                self.delete_button(item)
            else:
                messagebox.showerror("Permission Denied", "You cannot end another user's task.")

        def delete_button(self, item):
            if item in self.buttons:
                self.buttons[item].destroy()
                del self.buttons[item]

        def delete(self, *items):
            for item in items:
                self.delete_button(item)
            super().delete(*items)

        def resize(self):
            for item in self.get_children():
                if item in self.buttons:
                    self.place_button(item)

    def on_resize(event):
        global running_task_treeview_reference
        if 'running_task_treeview_reference' in globals():
            try:
                running_task_treeview_reference.resize()
            except tk.TclError:
                pass
    root.title("Mezzex Eye")
    root.geometry("1280x850")
    root.configure(fg_color="#2c3e50")
    root.iconbitmap(icon_path)

    def update_current_time():
        current_time = datetime.now(pytz.timezone(local_timezone)).strftime("%H:%M:%S")
        if current_time_label_reference and current_time_label_reference.winfo_exists():
            current_time_label_reference.configure(text=f"Current Time: {current_time}")
        root.after(1000, update_current_time)

    def on_close():
        show_login_screen()
        root.attributes('-fullscreen', True)

    root.protocol("WM_DELETE_WINDOW", on_close)
    show_login_screen()
    root.mainloop()

# Configure logging
logging.basicConfig(filename='app.log', level=logging.DEBUG)
if __name__ == "__main__":
    create_startup_task()
    main()
