import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
import requests
import pyautogui
from PIL import ImageOps
import psutil
import schedule
import time
import threading
import cloudinary
import cloudinary.uploader
import pytz
from datetime import datetime
import socket

# Cloudinary configuration
cloudinary.config(
    cloud_name='du0vb79mg',
    api_key='653838984145584',
    api_secret='f3V5J_bW3d0pebFOkDtZDv697OU'
)

TOKEN = None
USERNAME = None
USER_ID = None
STAFF_ID = None  # To save the staff ID after staff in
TASKS = []
TASKTIMEID = None
STAFF_IN_TIME = None
RUNNING_TASKS = {}
ENDED_TASKS = []
TASK_ID_MAP = {}  # To map task names to their IDs
SCREENSHOT_ENABLED = False  # Flag to control screenshot functionality
UPDATE_TASK_LIST_FLAG = False  # Flag to control task list updating

# URL for external time API
TIME_API_URL = "https://smapi.mezzex.com/api/ServerTime"

# Counter for unique task IDs
task_counter = 0

def get_external_time():
    try:
        response = requests.get(TIME_API_URL, verify=False)
        if response.status_code == 200:
            time_data = response.json()
            external_time_str = time_data['serverTimeIst']
            external_time = datetime.fromisoformat(external_time_str)
            return external_time
        return None
    except requests.exceptions.RequestException:
        return None

def is_system_time_valid():
    external_time = get_external_time()
    if not external_time:
        return False

    system_time = datetime.now()
    time_difference = abs((system_time - external_time).total_seconds())
    # Allow a difference of up to 5 minutes
    if time_difference > 300:
        return False
    return True

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

                # Fetch staff in time
                STAFF_IN_TIME, STAFF_ID = get_staff_in_time(USER_ID)
                
                return USERNAME, USER_ID
            return None, None
        return None, None
    except requests.exceptions.RequestException:
        return None, None
def get_staff_in_time(user_id):
    url = f"https://smapi.mezzex.com/api/Data/getStaffInTime?userId={user_id}"
    try:
        response = requests.get(url, verify=False)
        if response.status_code == 200:
            data = response.json()
            staff_in_time = datetime.fromisoformat(data['staffInTime'])
            staff_id = data['staffId']
            return staff_in_time, staff_id
        return None, None
    except requests.exceptions.RequestException:
        return None, None

def fetch_tasks():
    url = "https://smapi.mezzex.com/api/Data/getTasks"
    try:
        response = requests.get(url, verify=False)
        if response.status_code == 200:
            tasks = response.json()
            for task in tasks:
                TASK_ID_MAP[task['name']] = task['id']
            return tasks
        return []
    except requests.exceptions.RequestException:
        return []

def fetch_completed_tasks(user_id):
    url = f"https://smapi.mezzex.com/api/Data/getUserCompletedTasks?userId={user_id}"
    try:
        response = requests.get(url, verify=False)
        if response.status_code == 200:
            completed_tasks = response.json()
            return completed_tasks
        return []
    except requests.exceptions.RequestException:
        return []

def take_screenshot():
    if not SCREENSHOT_ENABLED:
        return
    
    screenshot = pyautogui.screenshot()
    # Use ImageOps to compress the image
    screenshot = ImageOps.exif_transpose(screenshot)
    image_url = upload_to_cloudinary(screenshot)
    if image_url:
        system_info = get_system_info()
        activity_log = get_activity_log()
        upload_data(image_url, system_info, activity_log)

def upload_to_cloudinary(screenshot):
    try:
        screenshot.save("screenshot_temp.jpg", "JPEG", quality=20, optimize=True)
        response = cloudinary.uploader.upload("screenshot_temp.jpg", upload_preset="ml_default")
        if 'url' in response:
            return response['url']
        return None
    except Exception:
        return None

def get_system_info():
    system_info = psutil.virtual_memory()
    system_name = socket.gethostname()  # Get the system name using socket.gethostname()
    return f"System Info: {system_info}, System Name: {system_name}"

def get_activity_log():
    # Implement activity log tracking here
    return "Activity Log"

def upload_data(image_url, system_info, activity_log):
    kolkata_tz = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(kolkata_tz).isoformat()  # Ensure ISO 8601 format
    system_name = socket.gethostname()  # Get the system name using socket.gethostname()

    url = "https://smapi.mezzex.com/api/Data/saveScreenCaptureData"
    data = {
        "ImageUrl": image_url,
        "CreatedOn": current_time,  # Include the timestamp from the Python code in ISO 8601 format
        "SystemName": system_name,  # Include the system name in the data
        "Username": USERNAME,  # Include the username in the data
        "TaskTimerId": TASKTIMEID
    }
    try:
        response = requests.post(url, json=data, verify=False)
        if response.status_code != 200:
            pass
    except requests.exceptions.RequestException:
        pass

def start_scheduled_tasks():
    schedule.every(5).minutes.do(take_screenshot)
    while True:
        schedule.run_pending()
        time.sleep(1)

def on_login_click(event=None):
    global TOKEN, USERNAME, USER_ID
    email = username_entry.get()  # Fetch the email from the entry
    password = password_entry.get()
    USERNAME, USER_ID = login(email, password)
    if USERNAME:
        show_task_management_screen(USERNAME, USER_ID)
        threading.Thread(target=start_scheduled_tasks).start()
    else:
        messagebox.showerror("Login Failed", "Invalid email or password.")

def show_task_management_screen(username, user_id):
    global UPDATE_TASK_LIST_FLAG, running_task_treeview_reference, ended_task_treeview_reference, current_time_label_reference
    UPDATE_TASK_LIST_FLAG = True

    for widget in root.winfo_children():
        widget.destroy()

    # Create a frame to hold the top row widgets
    top_row_frame = ctk.CTkFrame(root, fg_color="#2c3e50")
    top_row_frame.grid(row=0, column=0, columnspan=6, pady=10, sticky="ew")

    # Current time label in the left corner
    current_time_label = ctk.CTkLabel(top_row_frame, text="", font=("Helvetica", 12, "bold"), fg_color="#2c3e50", text_color="#ecf0f1")
    current_time_label.grid(row=0, column=0, sticky="w", padx=10)

    global current_time_label_reference
    current_time_label_reference = current_time_label
    update_current_time()

    # Welcome label in the center
    welcome_label = ctk.CTkLabel(top_row_frame, text=f"Welcome, {username}!", font=("Helvetica", 16, "bold"), fg_color="#2c3e50", text_color="#ecf0f1")
    welcome_label.grid(row=0, column=1, sticky="ew")

    # Refresh button in the right corner
    refresh_button = ctk.CTkButton(top_row_frame, text="Refresh", fg_color="#2980b9", text_color="#ecf0f1", font=("Helvetica", 12), command=refresh_ui, height=30, width=100)
    refresh_button.grid(row=0, column=2, sticky="e", padx=10)

    # Configure column weights for proper alignment
    top_row_frame.grid_columnconfigure(0, weight=1)
    top_row_frame.grid_columnconfigure(1, weight=3)
    top_row_frame.grid_columnconfigure(2, weight=1)

    # Staff in/out and time display section
    staff_buttons_frame = ctk.CTkFrame(root, fg_color="#2c3e50")
    staff_buttons_frame.grid(row=1, column=0, columnspan=6, pady=10, sticky="ew")

    staff_in_button = ctk.CTkButton(staff_buttons_frame, text="Staff In", fg_color="#3498db", text_color="#ecf0f1", font=("Helvetica", 12), command=staff_in, height=30, width=100)
    staff_in_button.pack(side="left", padx=12)
    staff_out_button = ctk.CTkButton(staff_buttons_frame, text="Staff Out", fg_color="#e74c3c", text_color="#ecf0f1", font=("Helvetica", 12), command=staff_out, height=30, width=100)
    staff_out_button.pack(side="left", padx=12)

    staff_in_time_label = ctk.CTkLabel(staff_buttons_frame, text="Staff In Time: Not Logged In", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12, "bold"))
    staff_in_time_label.pack(side="left", padx=12)

    global staff_in_button_reference, staff_in_time_label_reference
    staff_in_button_reference = staff_in_button
    staff_in_time_label_reference = staff_in_time_label

    # Fetch tasks from the API
    tasks = fetch_tasks()
    task_names = [task["name"] for task in tasks] + ["Other"]

    # Task input section
    ctk.CTkLabel(root, text="Task Type:", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12, "bold")).grid(row=2, column=0, padx=10, pady=10, sticky="w")
    task_type_combobox = ctk.CTkComboBox(root, values=task_names, font=("Helvetica", 12), width=250, height=30)  # Set initial width and height
    task_type_combobox.grid(row=2, column=1, padx=2, pady=10, sticky="ew")  # Reduced padding
    task_type_combobox.bind("<<ComboboxSelected>>", lambda event: on_task_selected(task_type_combobox, task_type_entry))
    task_type_combobox.set("Select Task Type")  # Set default text

    task_type_entry = ctk.CTkEntry(root, font=("Helvetica", 12), width=250, height=30)  # Set initial width and height
    task_type_entry.grid(row=2, column=2, padx=2, pady=10, sticky="ew")  # Reduced padding
    task_type_entry.grid_remove()

    ctk.CTkLabel(root, text="Comment:", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12, "bold")).grid(row=2, column=3, padx=10, pady=10, sticky="w")  # Reduced padding
    comment_entry = ctk.CTkEntry(root, font=("Helvetica", 12), width=200, height=30)  # Set initial width and height
    comment_entry.grid(row=2, column=4, padx=2, pady=10, sticky="ew")  # Reduced padding

    start_task_button = ctk.CTkButton(root, text="Start Task", fg_color="#27ae60", text_color="#ecf0f1", font=("Helvetica", 12), command=lambda: start_task(task_type_combobox, task_type_entry, comment_entry), height=30, width=100)
    start_task_button.grid(row=2, column=5, padx=10, pady=10, sticky="ew")

    # Bind Enter key to Start Task button
    root.bind("<Return>", lambda event: start_task(task_type_combobox, task_type_entry, comment_entry))

    # Running task list section
    ctk.CTkLabel(root, text="Running Tasks", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12, "bold")).grid(row=3, column=0, columnspan=6, pady=5, padx=10, sticky="w")

    running_task_list_frame = tk.Frame(root, bg="#ecf0f1")
    running_task_list_frame.grid(row=4, column=0, columnspan=6, padx=10, pady=5, sticky="nsew")

    # Configure Treeview for Running Tasks
    running_task_treeview = CustomTreeview(running_task_list_frame, columns=("Staff Name", "Task Type", "Comment", "Start Time", "Working Time", "End Task"), show="headings", selectmode="none")
    running_task_treeview.pack(expand=True, fill="both")

    for col in running_task_treeview["columns"]:
        running_task_treeview.heading(col, text=col, anchor="w")
        running_task_treeview.column(col, anchor="w")

    running_task_treeview_reference = running_task_treeview

    # Ended task list section
    ctk.CTkLabel(root, text="Ended Tasks", fg_color="#2c3e50", text_color="#ecf0f1", font=("Helvetica", 12, "bold")).grid(row=5, column=0, columnspan=6, pady=5, padx=10, sticky="w")

    ended_task_list_frame = tk.Frame(root, bg="#ecf0f1")
    ended_task_list_frame.grid(row=6, column=0, columnspan=6, padx=10, pady=5, sticky="nsew")

    # Configure Treeview for Ended Tasks
    ended_task_treeview = CustomTreeview(ended_task_list_frame, columns=("Staff Name", "Task Type", "Comment", "Start Time", "End Time", "Working Time"), show="headings", selectmode="none")
    ended_task_treeview.pack(expand=True, fill="both")

    for col in ended_task_treeview["columns"]:
        ended_task_treeview.heading(col, text=col, anchor="w")
        ended_task_treeview.column(col, anchor="w")

    ended_task_treeview_reference = ended_task_treeview

    # Fetch task timers from the API
    task_timers = fetch_task_timers()
    for task in task_timers:
        task_id = len(RUNNING_TASKS)
        RUNNING_TASKS[task_id] = {
            "staff_name": task["userName"],
            "task_type": task["taskName"],
            "comment": task["taskComment"],
            "start_time": datetime.fromisoformat(task["taskStartTime"]).strftime("%Y-%m-%dT%H:%M:%S"),
            "working_time": "00:00:00"
        }

    # Clear the ENDED_TASKS list before adding new tasks
    ENDED_TASKS.clear()

    # Fetch completed tasks for the user and add to ENDED_TASKS
    completed_tasks = fetch_completed_tasks(user_id)
    for task in completed_tasks:
        ended_task = {
            "staff_name": task["userName"],
            "task_type": task["taskName"],
            "comment": task["taskComment"],
            "start_time": datetime.fromisoformat(task["taskStartTime"]).strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time": datetime.fromisoformat(task["taskEndTime"]).strftime("%Y-%m-%dT%H:%M:%S"),
            "working_time": str(datetime.fromisoformat(task["taskEndTime"]) - datetime.fromisoformat(task["taskStartTime"]))
        }
        ENDED_TASKS.append(ended_task)

    update_task_list()

    # Make rows and columns expandable, setting lower weights for the task areas
    for i in range(7):
        root.grid_rowconfigure(i, weight=0)
    root.grid_rowconfigure(4, weight=1)
    root.grid_rowconfigure(6, weight=1)
    for i in range(6):
        root.grid_columnconfigure(i, weight=1)

def on_task_selected(task_type_combobox, task_type_entry):
    selected_task = task_type_combobox.get()
    if (selected_task == "Other") and (task_type_entry):
        task_type_entry.grid()
    elif task_type_entry:
        task_type_entry.grid_remove()

def start_task(task_type_combobox, task_type_entry, comment_entry):
    global TASKS, task_counter
    if STAFF_IN_TIME is None:
        staff_in()

    # Validate system time before starting a task
    # if not is_system_time_valid():
    #     messagebox.showerror("Time Error", "System time has been altered. Please correct the time and try again.")
    #     return

    # Check if task type is selected
    task_type = task_type_combobox.get()
    if task_type == "Select Task Type":
        messagebox.showerror("Error", "Please select a task type.")
        return

    # Check if there are any running tasks for the logged-in user
    for task in RUNNING_TASKS.values():
        if task["staff_name"] == USERNAME and "end_time" not in task:
            messagebox.showerror("Task Error", "Please close the previous task before starting a new one.")
            return

    if task_type == "Other":
        task_type = task_type_entry.get()
        if not comment_entry.get():
            messagebox.showerror("Error", "Comment cannot be empty for 'Other' task type.")
            return
    
    comment = comment_entry.get()
    
    task_id = TASK_ID_MAP.get(task_type, 1)  # Get the TaskId for the selected task or default to 1 if not found
    task = {"task_type": task_type, "comment": comment, "start_time": datetime.now(), "task_id": task_id}
    TASKS.append(task)
    save_task(task)

    task_counter += 1  # Ensure unique task ID
    start_task_record(task_counter, task)
    task_type_combobox.set("Select Task Type")  # Reset combobox text
    task_type_entry.delete(0, tk.END)
    comment_entry.delete(0, tk.END)
    update_task_list()

def save_task(task):
    url = "https://smapi.mezzex.com/api/Data/saveTaskTimer"
    data = {
        "UserId": USER_ID,  # Use the fetched UserId
        "TaskId": task["task_id"],  # Use the selected TaskId from TASK_ID_MAP
        "TaskComment": task["comment"],
        "taskStartTime": task["start_time"].isoformat(),
        "taskEndTime": None  # Task has just started, so taskEndTime is None
    }

    try:
        response = requests.post(url, json=data, verify=False)
        if response.status_code == 200:
            response_json = response.json()
            if response_json.get("message") == "Task timer data uploaded successfully":
                global TASKTIMEID
                TASKTIMEID = response_json.get("taskTimeId")  # Ensure the key matches 'taskTimeId'
        else:
            pass
    except requests.exceptions.RequestException:
        pass

def save_staff_in_time():
    global STAFF_IN_TIME, STAFF_ID, SCREENSHOT_ENABLED
    STAFF_IN_TIME = datetime.now()
    SCREENSHOT_ENABLED = True
    data = {
        "staffInTime": STAFF_IN_TIME.isoformat(),
        "staffOutTime": None,
        "UserId": USER_ID  # Include the UserId in the staff data
    }
    url = "https://smapi.mezzex.com/api/Data/saveStaff"
    try:
        response = requests.post(url, json=data, verify=False)
        if response.status_code == 200:
            response_json = response.json()
            if response_json.get("message") == "Staff data saved successfully":
                STAFF_ID = response_json.get("staffId")  # Ensure the key matches 'staffId'
                
                # Update UI elements
                if staff_in_time_label_reference and staff_in_button_reference:
                    staff_in_time_label_reference.configure(text=f"Staff In Time: {STAFF_IN_TIME.strftime('%H:%M:%S')}")
                    staff_in_button_reference.configure(state=tk.DISABLED)
        else:
            pass
    except requests.exceptions.RequestException:
        pass

def update_staff_out_time():
    global STAFF_ID, SCREENSHOT_ENABLED
    if STAFF_IN_TIME is None:
        return
    
    if STAFF_ID is None:
        return
    
    SCREENSHOT_ENABLED = False
    staff_out_time = datetime.now()
    data = {
        "staffInTime": STAFF_IN_TIME.isoformat(),
        "staffOutTime": staff_out_time.isoformat(),
        "UserId": USER_ID,  # Include the UserId in the staff data
        "Id": STAFF_ID  # Include the StaffId to update the correct record
    }
    url = "https://smapi.mezzex.com/api/Data/updateStaff"
    
    try:
        response = requests.post(url, json=data, verify=False)
        if response.status_code == 200:
            pass
        else:
            pass
    except requests.exceptions.RequestException:
        pass

def start_task_record(task_counter, task):
    task_id = task_counter  # Ensure unique task ID
    start_time = task["start_time"]
    start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")  # Keep full ISO format for internal use

    RUNNING_TASKS[task_id] = {
        "staff_name": USERNAME,
        "task_type": task["task_type"],
        "comment": task["comment"],
        "start_time": start_time_str,  # Store in full ISO format for accurate time calculations
        "working_time": "00:00:00"
    }

def end_task(task_id):
    task = RUNNING_TASKS.get(int(task_id))
    if task is None:
        return

    # Ensure only the task owner can end the task
    if task["staff_name"] != USERNAME:
        messagebox.showerror("Permission Denied", "You cannot end another user's task.")
        return

    task = RUNNING_TASKS.pop(int(task_id))
    task["end_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")  # Store in full ISO format
    start_time = datetime.fromisoformat(task["start_time"])
    end_time = datetime.fromisoformat(task["end_time"])
    task["working_time"] = str(end_time - start_time).split(".")[0]  # Calculate total working time
    ENDED_TASKS.append(task)
    update_task_timer(task)

def update_task_timer(task):
    global TASKTIMEID
    # Ensure TASKTIMEID is set and is an integer
    if TASKTIMEID is None or not isinstance(TASKTIMEID, int):
        print("Error: Invalid TASKTIMEID. TASKTIMEID should be a non-null integer.")
        return

    url = "https://smapi.mezzex.com/api/Data/updateTaskTimer"
    data = {
        "id": TASKTIMEID,  # Ensure TaskTimeId is correctly set
        "taskEndTime": task["end_time"]  # Updated end time
    }

    # Debugging print statements
    print(f"Sending PUT request to {url} with data: {data}")

    try:
        response = requests.post(url, json=data, verify=False)
        print(f"Response status code: {response.status_code}")  # Debugging info
        if response.status_code == 200:
            print("Task end time updated successfully")
        else:
            print(f"Failed to update task end time: {response.status_code}, response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Request exception: {e}")

def end_all_running_tasks():
    for task_id in list(RUNNING_TASKS.keys()):
        task = RUNNING_TASKS[task_id]
        if task["staff_name"] == USERNAME:
            end_task(task_id)

def fetch_task_timers():
    url = "https://smapi.mezzex.com/api/Data/getTaskTimers"
    try:
        response = requests.get(url, verify=False)
        if response.status_code == 200:
            task_timers = response.json()
            return task_timers
        return []
    except requests.exceptions.RequestException:
        return []
def format_working_time(working_time_str):
    time_parts = working_time_str.split(':')
    
    if len(time_parts) == 3:
        hours, minutes, seconds = int(time_parts[0]), int(time_parts[1]), int(float(time_parts[2]))
    elif len(time_parts) == 2:
        hours, minutes, seconds = 0, int(time_parts[0]), int(float(time_parts[1]))
    else:
        hours, minutes, seconds = 0, 0, int(float(time_parts[0]))

    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if seconds > 0:
        parts.append(f"{seconds} second{'s' if seconds > 1 else ''}")
    return ' '.join(parts)

def update_task_list():
    if not UPDATE_TASK_LIST_FLAG:
        return

    # Update running tasks
    for task_id, task in RUNNING_TASKS.items():
        if "end_time" not in task:
            start_time = datetime.fromisoformat(task["start_time"])
            current_time = datetime.now()
            working_time = current_time - start_time
            task["working_time"] = str(working_time).split(".")[0]  # Exclude microseconds

    existing_items = set(running_task_treeview_reference.get_children())
    current_items = set(str(task_id) for task_id in RUNNING_TASKS.keys())

    # Update existing items and add new ones
    for task_id, task in RUNNING_TASKS.items():
        start_time = datetime.fromisoformat(task["start_time"])
        if str(task_id) in existing_items:
            # Update existing item if values have changed
            current_values = running_task_treeview_reference.item(str(task_id), "values")
            new_values = (
                task["staff_name"], task["task_type"], task["comment"], start_time.strftime("%H:%M:%S"),
                task["working_time"], ""
            )
            if current_values != new_values:
                running_task_treeview_reference.item(str(task_id), values=new_values)
        else:
            # Add new item
            if task["staff_name"] == USERNAME:
                running_task_treeview_reference.insert("", "end", iid=str(task_id), values=(
                    task["staff_name"], task["task_type"], task["comment"], start_time.strftime("%H:%M:%S"),
                    task["working_time"], ""), tags=("end_task", "current_user"))
            else:
                running_task_treeview_reference.insert("", "end", iid=str(task_id), values=(
                    task["staff_name"], task["task_type"], task["comment"], start_time.strftime("%H:%M:%S"),
                    task["working_time"], ""), tags=("end_task",))

    # Remove items that are no longer needed
    for item in existing_items - current_items:
        running_task_treeview_reference.delete(item)

    # Bind the End Task button
    running_task_treeview_reference.bind("<Button-1>", on_treeview_click)

    # Update ended tasks
    existing_ended_items = set(ended_task_treeview_reference.get_children())
    ended_task_treeview_reference.delete(*existing_ended_items)  # Clear existing ended task entries

    for task in ENDED_TASKS:
        start_time = datetime.fromisoformat(task["start_time"])
        end_time = datetime.fromisoformat(task["end_time"])
        working_time_str = format_working_time(task["working_time"])
        ended_task_treeview_reference.insert("", "end", values=(
            task["staff_name"], task["task_type"], task["comment"], start_time.strftime("%H:%M:%S"),
            end_time.strftime("%H:%M:%S"), working_time_str))

    root.after(1000, update_task_list)

def on_treeview_click(event):
    item = running_task_treeview_reference.identify('item', event.x, event.y)
    column = running_task_treeview_reference.identify_column(event.x)
    if column == '#6':  # 'End Task' column (last column)
        task_id = item
        end_task(task_id)

def staff_in():
    # Validate system time before staff in
    external_time = get_external_time()
    if external_time:
        STAFF_IN_TIME = external_time
    save_staff_in_time()

def staff_out():
    update_staff_out_time()
    end_all_running_tasks()
    staff_in_button_reference.configure(state=tk.NORMAL)
    show_login_screen()  # Navigate back to login screen

def show_login_screen():
    global UPDATE_TASK_LIST_FLAG, username_entry, password_entry, show_password_var
    UPDATE_TASK_LIST_FLAG = False
    for widget in root.winfo_children():
        widget.destroy()
    # Redesigned Login screen
    login_frame = ctk.CTkFrame(root, fg_color="#2c3e50", corner_radius=15)
    login_frame.pack(expand=True)
    login_title = ctk.CTkLabel(login_frame, text="Mezzex Eye Management System", font=("Helvetica", 24, "bold"), fg_color="#2c3e50", text_color="#ecf0f1", pady=20)
    login_title.grid(row=0, column=0, columnspan=2, pady=(20, 10), padx=10, sticky="n")
    username_label = ctk.CTkLabel(login_frame, text="Username:", font=("Helvetica", 14), fg_color="#2c3e50", text_color="#ecf0f1", padx=10, pady=5)
    username_label.grid(row=1, column=0, pady=10, sticky="e")
    username_entry = ctk.CTkEntry(login_frame, font=("Helvetica", 14), width=250)
    username_entry.grid(row=1, column=1, pady=10, padx=(0, 10), sticky="w")
    password_label = ctk.CTkLabel(login_frame, text="Password:", font=("Helvetica", 14), fg_color="#2c3e50", text_color="#ecf0f1", padx=10, pady=5)
    password_label.grid(row=2, column=0, pady=10, sticky="e")
    password_frame = tk.Frame(login_frame, bg="#2c3e50")
    password_frame.grid(row=2, column=1, pady=10, padx=(0, 10), sticky="w")
    password_entry = ctk.CTkEntry(password_frame, font=("Helvetica", 14), show="*", width=230)
    password_entry.grid(row=0, column=0, sticky="w")
    show_password_var = tk.BooleanVar()
    show_password_checkbutton = ctk.CTkCheckBox(password_frame, text="Show", variable=show_password_var, command=toggle_password_visibility)
    show_password_checkbutton.grid(row=0, column=1, padx=(10, 0), sticky="w")
    login_button = ctk.CTkButton(login_frame, text="Login", font=("Helvetica", 14), fg_color="#3498db", text_color="#ecf0f1", hover_color="#2980b9", command=on_login_click, width=100, height=30)
    login_button.grid(row=3, column=0, columnspan=2, pady=20)
    # Bind Enter key to Login button
    root.bind("<Return>", on_login_click)
    # Make rows and columns expandable
    login_frame.grid_rowconfigure(0, weight=1)
    login_frame.grid_rowconfigure(1, weight=1)
    login_frame.grid_rowconfigure(2, weight=1)
    login_frame.grid_rowconfigure(3, weight=1)
    login_frame.grid_columnconfigure(0, weight=1)
    login_frame.grid_columnconfigure(1, weight=1)

def toggle_password_visibility():
    global password_entry, show_password_var
    if show_password_var.get():
        password_entry.configure(show="")
    else:
        password_entry.configure(show="*")

def refresh_ui():
    global USER_ID, running_task_treeview_reference, ended_task_treeview_reference
    # Fetch latest tasks, completed tasks, and task timers
    fetch_tasks()
    fetch_completed_tasks(USER_ID)
    fetch_task_timers()
    update_task_list()  # Add this line to refresh the UI
    print("Refreshed UI")  # Add this line for debugging

class CustomTreeview(ttk.Treeview):
    def __init__(self, master=None, **kwargs):
        super(CustomTreeview, self).__init__(master, **kwargs)
        self.style = ttk.Style()
        self.style.configure("Treeview", font=("Helvetica", 12), rowheight=30)
        self.style.configure("Treeview.Heading", font=("Helvetica", 12, "bold"))  # Adjusted boldness
        self.buttons = {}  # To store buttons for each item
    def insert(self, parent, index, iid=None, **kw):
        item = super(CustomTreeview, self).insert(parent, index, iid=iid, **kw)
        if 'tags' in kw and 'end_task' in kw['tags']:
            self.add_button(item)
        return item
    def add_button(self, item):
        if item not in self.buttons:
            btn = ttk.Button(self, text="End Task", command=lambda: self.end_task_callback(item), style="Custom.TButton")
            self.buttons[item] = btn
            self.place_button(item)
            self.update_idletasks()
    def place_button(self, item):
        if item in self.buttons:
            btn = self.buttons[item]
            bbox = self.bbox(item, column="#6")  # Adjusted to column #6
            if bbox:
                btn.place(x=bbox[0] + 2, y=bbox[1] + 2)  # Adjusted x coordinate to remove space
    def end_task_callback(self, item):
        task_id = item
        task = RUNNING_TASKS.get(int(task_id))
        if task is not None and task["staff_name"] == USERNAME:
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
        super(CustomTreeview, self).delete(*items)
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

root = ctk.CTk()
root.title("Mezzex Eye Management System")
root.geometry("1280x850")
root.configure(fg_color="#2c3e50")

def on_resize(event):
    global running_task_treeview_reference
    if 'running_task_treeview_reference' in globals():
        try:
            running_task_treeview_reference.resize()
        except tk.TclError:
            pass
root.bind("<Configure>", on_resize)

def update_current_time():
    current_time = datetime.now().strftime("%H:%M:%S")
    if current_time_label_reference:
        current_time_label_reference.configure(text=f"Current Time: {current_time}")
    root.after(1000, update_current_time)

def on_close():
    try:
        staff_out()
    except Exception as e:
        print(f"Error during staff out: {e}")
    finally:
        root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)
show_login_screen()
root.mainloop()
