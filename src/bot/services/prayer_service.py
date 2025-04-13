# import aiosqlite
# from datetime import datetime, timedelta
# from src.config.settings import DATABASE_PATH, REVERSE_LOCATION_MAP
# from src.config.constants import PRAYER_EMOJIS
# from src.scraping.prayer_times import fetch_cached_prayer_times
# from src.bot.utils.calculations import calculate_islamic_date
#
#
# async def get_prayer_message(chat_id: int, region: str | None, day_type: str = "bugun") -> tuple[str, str, str, str]:
#     # Start building the message with location, date, and Islamic date
#     message_text = (
#         f"📍 {times['location']}\n"
#         f"🗓 {times['date']}\n"
#         f"☪️ {islamic_date}\n"
#         f"------------------------\n"
#     )
#
#     # Add prayer times table with emojis, bold, and tick for 'bugun', or just list for 'erta'
#     if day_type == 'bugun':
#         # Find the closest (exact) prayer time to now
#         closest_prayer = None
#         min_time_diff = None
#         for prayer, time_str in times['prayer_times'].items():
#             if time_str != 'N/A':
#                 prayer_minutes = int(time_str.split(':')[0]) * 60 + int(time_str.split(':')[1])
#                 current_minutes = int(current_time.split(':')[0]) * 60 + int(current_time.split(':')[1])
#                 time_diff = prayer_minutes - current_minutes
#                 if (min_time_diff is None or
#                         (time_diff <= 0 and (min_time_diff > 0 or time_diff > min_time_diff)) or
#                         (time_diff > 0 and time_diff < min_time_diff)):
#                     closest_prayer = prayer
#                     min_time_diff = time_diff
#
#         # Build prayer list with emojis, bolding exact time, and adding tick
#         for prayer, time_str in times['prayer_times'].items():
#             emoji = PRAYER_EMOJIS.get(prayer, '⏰')
#             if prayer == closest_prayer:
#                 # Use blockquote with bold for the closest prayer
#                 message_text += f"<blockquote><b>{emoji} {prayer}: {time_str}</b></blockquote>\n"
#             else:
#                 # Regular formatting for other prayers
#                 message_text += f"{emoji} {prayer}: {time_str}\n"
#     else:  # 'erta'
#         # Build simple prayer list with emojis for tomorrow
#         for prayer, time_str in times['prayer_times'].items():
#             emoji = PRAYER_EMOJIS.get(prayer, '⏰')
#             message_text += f"{emoji} {prayer}: {time_str}\n"
#
#     message_text += f"------------------------\n"
#
#     # Add next prayer countdown only for 'bugun'
#     if day_type == 'bugun' and next_prayer and next_prayer_time != 'N/A':
#         message_text += (
#             f"<code><b>{next_prayer}</b> gacha <b>-{countdown}</b> qoldi</code>"
#         )
#     elif day_type == 'bugun' and closest_prayer == "Xufton" and (not next_prayer or next_prayer_time == 'N/A'):
#         # All prayers for today have passed (Xufton is the closest and no next prayer)
#         tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
#         tomorrow_times = await fetch_cached_prayer_times(region, tomorrow_date)
#         if tomorrow_times:
#             # Get Bomdod time for tomorrow
#             bomdod_time = tomorrow_times['prayer_times'].get('Bomdod', 'N/A')
#             if bomdod_time != 'N/A':
#                 try:
#                     next_time = datetime.strptime(bomdod_time, "%H:%M")
#                     next_time = datetime.now().replace(
#                         hour=next_time.hour,
#                         minute=next_time.minute,
#                         second=0,
#                         microsecond=0
#                     ) + timedelta(days=1)  # Set to tomorrow
#                     time_until = next_time - datetime.now()
#                     hours, remainder = divmod(time_until.seconds, 3600)
#                     minutes, seconds = divmod(remainder, 60)
#                     countdown = f"{hours}:{minutes:02d}"
#                     message_text += (
#                         f"<code>Bomdod gacha-{countdown} qoldi</code>"
#                     )
#                 except Exception as e:
#                     logger.error(f"Error calculating countdown to tomorrow's Bomdod: {str(e)}")
#
#     # Send the formatted message with Markdown parsing for bold
#     sent_message = await message.answer(message_text, parse_mode='HTML')
