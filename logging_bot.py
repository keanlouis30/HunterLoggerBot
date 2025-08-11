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
# On Render, these will be set in the dashboard instead
load_dotenv() 

# --- Cloud-Ready Configuration ---
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
WORKBOOK_NAME = os.getenv('WORKBOOK_NAME', 'Hunter_Logging') # Default to 'Hunter_Logging' if not set

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

# This logic checks for credentials in Render's secret file path first,
# then falls back to the local path for testing.
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
    print(f"Successfully connected to Google Sheet: '{WORKBOOK_NAME}'")
except Exception as e:
    print(f"CRITICAL ERROR: Could not connect to Google Sheets. Check credentials and workbook name. Error: {e}")
    exit()

# --- ASYNCHRONOUS HELPER FUNCTIONS (No changes needed here) ---

async def run_blocking(blocking_func, *args, **kwargs):
    func = functools.partial(blocking_func, *args, **kwargs)
    return await client.loop.run_in_executor(None, func)

async def find_last_login(user_display_name):
    try:
        all_logins = await run_blocking(login_sheet.get_all_values)
        last_login_datetime = None
        current_date_str = None
        for row in reversed(all_logins):
            if len(row) > 0 and row[0] and (len(row) == 1 or not row[1]):
                try:
                    datetime.strptime(row[0], '%B %d, %Y')
                    current_date_str = row[0]
                except (ValueError, IndexError):
                    continue
            elif len(row) > 1 and row[1] == user_display_name and current_date_str:
                login_time_str = row[0]
                full_datetime_str = f"{current_date_str} {login_time_str}"
                naive_datetime = datetime.strptime(full_datetime_str, '%B %d, %Y %I:%M:%S %p')
                last_login_datetime = manila_tz.localize(naive_datetime)
                return last_login_datetime
        return None
    except Exception as e:
        print(f"An error occurred while finding last login: {e}")
        return None

async def add_log_entry(sheet, user, color=None):
    now_manila = datetime.now(manila_tz)
    today_str = now_manila.strftime('%B %d, %Y')
    now_time_str = now_manila.strftime('%I:%M:%S %p')
    roles = [role.name for role in user.roles if role.name != "@everyone"]
    new_row_data = [now_time_str, user.display_name, ', '.join(roles)]
    all_values = await run_blocking(sheet.get_all_values)
    header_row_index = -1
    for i, row in enumerate(all_values):
        if row and row[0] == today_str:
            header_row_index = i
            break
    is_new_date_group = (header_row_index == -1)
    data_row_format = None
    if color == 'green':
        data_row_format = CellFormat(backgroundColor=Color(0.75, 1, 0.75))
    elif color == 'red':
        data_row_format = CellFormat(backgroundColor=Color(1, 0.75, 0.75))
    elif color == 'blue':
        data_row_format = CellFormat(backgroundColor=Color(0.75, 0.85, 1))
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
        while next_row_index < len(all_values) and all_values[next_row_index]:
            next_row_index += 1
        new_row_num = next_row_index + 1
        await run_blocking(sheet.insert_row, new_row_data, new_row_num, value_input_option='USER_ENTERED')
    if data_row_format:
        await run_blocking(format_cell_range, sheet, f'A{new_row_num}:C{new_row_num}', data_row_format)

# --- Discord Bot Events (No changes needed here) ---

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    print(f'Current time in Manila: {datetime.now(manila_tz).strftime("%Y-%m-%d %H:%M:%S")}')

@client.event
async def on_message(message):
    if message.guild is None or message.author == client.user:
        return
    if message.content.lower() == '@login':
        user = message.author
        await add_log_entry(login_sheet, user, color='green')
        await message.channel.send(f'Welcome, {user.mention}! Your login has been recorded in PH time.')
    if message.content.lower() == '@logout':
        user = message.author
        last_login = await find_last_login(user.display_name)
        logout_color = None
        if last_login:
            now_manila = datetime.now(manila_tz)
            duration = now_manila - last_login
            if duration < timedelta(hours=8):
                logout_color = 'red'
            else:
                logout_color = 'blue'
        await add_log_entry(logout_sheet, user, color=logout_color)
        await message.channel.send(f'Goodbye, {user.mention}! Your logout has been recorded in PH time.')

# --- Run the Bot ---
if not TOKEN:
    print("CRITICAL ERROR: DISCORD_BOT_TOKEN not found in environment variables.")
else:
    try:
        client.run(TOKEN)
    except discord.errors.LoginFailure:
        print("CRITICAL ERROR: Improper token has been passed via environment variable.")