import discord
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_formatting import *
from datetime import datetime, timedelta
import pytz
import os
from dotenv import load_dotenv
import functools

# --- Load Environment Variables for local development ---
load_dotenv() 

# --- Cloud-Ready Configuration ---
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
WORKBOOK_NAME = os.getenv('WORKBOOK_NAME', 'Hunter_Logging')

# --- Discord Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)

# --- Cloud-Ready Google Sheets & Timezone Setup ---
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
manila_tz = pytz.timezone('Asia/Manila')

render_creds_path = '/etc/secrets/credentials.json'
local_creds_path = 'credentials.json'

if os.path.exists(render_creds_path):
    creds_path = render_creds_path
    print("Using Render's secret file for credentials.")
else:
    creds_path = local_creds_path
    print("Using local 'credentials.json' file.")

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    gspread_client = gspread.authorize(creds)
    workbook = gspread_client.open(WORKBOOK_NAME)
    login_sheet = workbook.worksheet("Log In")
    logout_sheet = workbook.worksheet("Log Out")
    
    # Try to get the Statistics sheet, or create it if it doesn't exist
    try:
        stats_sheet = workbook.worksheet("Statistics")
    except gspread.exceptions.WorksheetNotFound:
        print("Creating 'Statistics' sheet...")
        stats_sheet = workbook.add_worksheet(title="Statistics", rows="100", cols="20")

    print(f"Successfully connected to Google Sheet: '{WORKBOOK_NAME}'")
except Exception as e:
    print(f"CRITICAL ERROR: Could not connect to Google Sheets. Check credentials and workbook name. Error: {e}")
    exit()

# --- ASYNCHRONOUS HELPER FUNCTIONS ---

async def run_blocking(blocking_func, *args, **kwargs):
    func = functools.partial(blocking_func, *args, **kwargs)
    return await client.loop.run_in_executor(None, func)

async def find_last_login(user_display_name):
    # This function remains unchanged
    try:
        all_logins = await run_blocking(login_sheet.get_all_values)
        last_login_datetime = None
        current_date_str = None
        for row in reversed(all_logins):
            if len(row) > 0 and row[0] and (len(row) == 1 or not row[1]):
                try:
                    datetime.strptime(row[0], '%B %d, %Y'); current_date_str = row[0]
                except (ValueError, IndexError): continue
            elif len(row) > 1 and row[1] == user_display_name and current_date_str:
                login_time_str = row[0]
                full_datetime_str = f"{current_date_str} {login_time_str}"
                naive_datetime = datetime.strptime(full_datetime_str, '%B %d, %Y %I:%M:%S %p')
                last_login_datetime = manila_tz.localize(naive_datetime)
                return last_login_datetime
        return None
    except Exception as e:
        print(f"An error occurred while finding last login: {e}"); return None

async def add_log_entry(sheet, user, color=None):
    # This function remains unchanged
    now_manila = datetime.now(manila_tz)
    today_str = now_manila.strftime('%B %d, %Y')
    now_time_str = now_manila.strftime('%I:%M:%S %p')
    roles = [role.name for role in user.roles if role.name != "@everyone"]
    new_row_data = [now_time_str, user.display_name, ', '.join(roles)]
    all_values = await run_blocking(sheet.get_all_values)
    header_row_index = -1
    for i, row in enumerate(all_values):
        if row and row[0] == today_str: header_row_index = i; break
    is_new_date_group = (header_row_index == -1)
    data_row_format = None
    if color == 'green': data_row_format = CellFormat(backgroundColor=Color(0.75, 1, 0.75))
    elif color == 'red': data_row_format = CellFormat(backgroundColor=Color(1, 0.75, 0.75))
    elif color == 'blue': data_row_format = CellFormat(backgroundColor=Color(0.75, 0.85, 1))
    new_row_num = 0
    if is_new_date_group:
        header_format = CellFormat(backgroundColor=Color(0.87, 0.92, 0.99), textFormat=TextFormat(bold=True))
        new_header_row_num = len(all_values) + 1
        await run_blocking(sheet.append_row, [today_str], value_input_option='USER_ENTERED')
        await run_blocking(sheet.append_row, ['Time', 'Name', 'Role'], value_input_option='USER_ENTERED')
        await run_blocking(sheet.append_row, new_row_data, value_input_option='USER_ENTERED')
        await run_blocking(format_cell_range, sheet, f'A{new_header_row_num}', header_format)
        new_row_num = new_header_row_num + 2
    else:
        next_row_index = header_row_index + 2
        while next_row_index < len(all_values) and all_values[next_row_index]: next_row_index += 1
        new_row_num = next_row_index + 1
        await run_blocking(sheet.insert_row, new_row_data, new_row_num, value_input_option='USER_ENTERED')
    if data_row_format:
        await run_blocking(format_cell_range, sheet, f'A{new_row_num}:C{new_row_num}', data_row_format)

# --- NEW STATISTICS GENERATION FUNCTION ---

def parse_sheet_data(all_values, target_month, target_year):
    """Helper to parse raw sheet data into a list of (datetime, user) tuples for a specific month."""
    parsed_data = []
    current_date_str = None
    for row in all_values:
        if len(row) > 0 and row[0] and (len(row) == 1 or not row[1]):
            try:
                dt = datetime.strptime(row[0], '%B %d, %Y')
                if dt.month == target_month and dt.year == target_year:
                    current_date_str = row[0]
                else:
                    current_date_str = None # Reset if it's not the target month
            except (ValueError, IndexError): continue
        elif len(row) > 1 and row[1] and current_date_str:
            try:
                time_str = row[0]
                user_name = row[1]
                full_datetime_str = f"{current_date_str} {time_str}"
                full_datetime = manila_tz.localize(datetime.strptime(full_datetime_str, '%B %d, %Y %I:%M:%S %p'))
                parsed_data.append((full_datetime, user_name))
            except (ValueError, IndexError): continue
    return parsed_data

async def generate_monthly_stats():
    """Fetches all data, calculates monthly stats, and writes a report to the 'Statistics' sheet."""
    now = datetime.now(manila_tz)
    target_month, target_year = now.month, now.year

    # 1. Fetch and parse data from both sheets
    login_values = await run_blocking(login_sheet.get_all_values)
    logout_values = await run_blocking(logout_sheet.get_all_values)
    
    logins = parse_sheet_data(login_values, target_month, target_year)
    logouts = parse_sheet_data(logout_values, target_month, target_year)
    
    # 2. Process data to calculate hours and login counts for each user
    user_stats = {}
    all_users = set(u for _, u in logins) | set(u for _, u in logouts)

    for user in all_users:
        user_logins = sorted([t for t, u in logins if u == user])
        user_logouts = sorted([t for t, u in logouts if u == user])
        
        total_hours = 0
        
        # Pair logins with the next available logout
        for login_time in user_logins:
            next_logout = next((logout_time for logout_time in user_logouts if logout_time > login_time), None)
            if next_logout:
                duration = next_logout - login_time
                total_hours += duration.total_seconds() / 3600
                user_logouts.remove(next_logout) # A logout can only be used once
                
        user_stats[user] = {
            'hours': total_hours,
            'logins': len(user_logins)
        }
    
    # 3. Clear the old report and prepare new data for writing
    await run_blocking(stats_sheet.clear)
    report_rows = []
    
    report_title = f"Monthly Report for {now.strftime('%B %Y')}"
    report_rows.append([report_title])
    report_rows.append([]) # Spacer row
    
    if not user_stats:
        report_rows.append(["No user activity recorded for this month."])
        await run_blocking(stats_sheet.append_rows, report_rows, value_input_option='USER_ENTERED')
        return

    # Main stats table
    report_rows.append(['User', 'Total Logged Hours', 'Total Logins'])
    sorted_users = sorted(user_stats.items(), key=lambda item: item[1]['hours'], reverse=True)
    
    for user, data in sorted_users:
        report_rows.append([user, f"{data['hours']:.2f}", data['logins']])
        
    report_rows.append([]); report_rows.append([]) # Spacers

    # Summary table
    most_hours = max(user_stats.items(), key=lambda item: item[1]['hours'])
    least_hours = min(user_stats.items(), key=lambda item: item[1]['hours'])
    most_logins = max(user_stats.items(), key=lambda item: item[1]['logins'])
    least_logins = min(user_stats.items(), key=lambda item: item[1]['logins'])
    
    report_rows.append(['Monthly Summary'])
    report_rows.append(['Category', 'User', 'Value'])
    report_rows.append(['Most Hours', most_hours[0], f"{most_hours[1]['hours']:.2f} hours"])
    report_rows.append(['Least Hours', least_hours[0], f"{least_hours[1]['hours']:.2f} hours"])
    report_rows.append(['Most Logins', most_logins[0], f"{most_logins[1]['logins']} logins"])
    report_rows.append(['Least Logins', least_logins[0], f"{least_logins[1]['logins']} logins"])

    # 4. Write all data to the sheet at once
    await run_blocking(stats_sheet.append_rows, report_rows, value_input_option='USER_ENTERED')
    
    # 5. Apply formatting
    title_format = CellFormat(textFormat=TextFormat(bold=True, fontSize=14))
    header_format = CellFormat(textFormat=TextFormat(bold=True))
    await run_blocking(format_cell_range, stats_sheet, 'A1', title_format)
    await run_blocking(format_cell_range, stats_sheet, 'A3:C3', header_format)
    await run_blocking(format_cell_range, stats_sheet, 'A8', title_format)
    await run_blocking(format_cell_range, stats_sheet, 'A9:C9', header_format)


# --- Discord Bot Events ---

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    print(f'Current time in Manila: {datetime.now(manila_tz).strftime("%Y-%m-%d %H:%M:%S")}')

@client.event
async def on_message(message):
    if message.guild is None or message.author == client.user:
        return

    # --- LOGIN COMMAND ---
    if message.content.lower() == '@login':
        user = message.author
        await add_log_entry(login_sheet, user, color='green')
        await message.channel.send(f'Welcome, {user.mention}! Your login has been recorded in PH time.')

    # --- LOGOUT COMMAND ---
    elif message.content.lower() == '@logout':
        user = message.author
        last_login = await find_last_login(user.display_name)
        logout_color = None
        if last_login:
            now_manila = datetime.now(manila_tz)
            duration = now_manila - last_login
            if duration < timedelta(hours=8): logout_color = 'red'
            else: logout_color = 'blue'
        await add_log_entry(logout_sheet, user, color=logout_color)
        await message.channel.send(f'Goodbye, {user.mention}! Your logout has been recorded in PH time.')

    # --- STATISTICS COMMAND ---
    elif message.content.lower() == '@statistics':
        await message.channel.send("Generating monthly statistics report... This may take a moment.")
        try:
            await generate_monthly_stats()
            # Provide a link directly to the sheet for convenience
            sheet_url = f"https://docs.google.com/spreadsheets/d/{workbook.id}"
            await message.channel.send(f"✅ Monthly statistics report has been generated! You can view it here: {sheet_url}")
        except Exception as e:
            await message.channel.send(f"❌ An error occurred while generating the report: {e}")
            print(f"Statistics generation error: {e}")


# --- Run the Bot ---
if not TOKEN:
    print("CRITICAL ERROR: DISCORD_BOT_TOKEN not found in environment variables.")
else:
    try: client.run(TOKEN)
    except discord.errors.LoginFailure:
        print("CRITICAL ERROR: Improper token has been passed via environment variable.")