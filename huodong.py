from hoshino import priv
from .safeservice import SafeService
import time
from datetime import datetime, timedelta
import os
import re
import random
import base64
from PIL import Image, ImageDraw, ImageFont
import io
import json
from pathlib import Path
from nonebot import on_command, get_bot
from nonebot import scheduler
import pytz
import requests
import hoshino
from hoshino import R, Service, priv, util
from hoshino.typing import CQEvent

sv = SafeService('半月刊', enable_on_default=False, bundle='半月刊', help_='''
【半月刊】：完整图片版
【日常活动|日历|日程】：显示进行中的活动和明天开始的活动
【剧情活动|角色活动|活动】：只显示角色剧情活动
【up卡池|up|卡池】：显示当前卡池跟未来卡池
【免费十连】 - 免费十连活动
【公会战】- 公会战信息
【露娜塔】 - 露娜塔信息
【新开专】 - 新开专武信息
【斗技场】 - 斗技场信息
【庆典活动】 - 庆典和双倍活动
【sp地下城】 - sp地下城
【更新半月刊】
'''.strip())

# 获取 data.json 的绝对路径
DATA_FILE = Path(__file__).parent / "data.json"

def load_activity_data():
    # 检查文件是否存在
    if not DATA_FILE.exists():
        sv.logger.error(f"❌ data.json 文件不存在！路径：{DATA_FILE}")
        return []

    # 检查文件是否可读
    if not os.access(DATA_FILE, os.R_OK):
        sv.logger.error(f"❌ data.json 不可读！请检查权限。")
        return []

    # 尝试读取 JSON
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            sv.logger.info("✅ 成功加载 data.json")
            return data
    except json.JSONDecodeError as e:
        sv.logger.error(f"❌ data.json 格式错误: {e}")
        return []
    except Exception as e:
        sv.logger.error(f"❌ 无法读取 data.json: {e}")
        return []

# 加载数据
data = load_activity_data()

if not data:
    sv.logger.error("⚠️ 活动数据为空，请检查 data.json！")
else:
    sv.logger.info(f"📊 已加载 {len(data)} 条活动数据")

# 在文件顶部添加
last_data_hash = None  # 存储上次数据的哈希值

# 计算数据哈希的函数
def calculate_data_hash(data):
    import hashlib
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.md5(data_str.encode('utf-8')).hexdigest()

# 修改更新函数，返回是否有更新
async def update_half_monthly_data():
    global data, last_data_hash
    
    try:
        github_url = "https://raw.githubusercontent.com/duoshoumiao/PCR--Fortnightly-magazine-/main/data.json"
        response = requests.get(github_url, timeout=15)
        response.raise_for_status()
        
        # 验证JSON格式
        try:
            new_data = json.loads(response.text)
        except json.JSONDecodeError:
            sv.logger.error("下载的数据不是有效的JSON格式")
            return False
            
        # 计算新数据的哈希
        new_hash = calculate_data_hash(new_data)
        
        # 如果没有变化
        if new_hash == last_data_hash:
            sv.logger.info("数据无变化，无需更新")
            return False
            
        # 创建备份
        backup_path = DATA_FILE.with_suffix('.json.bak')
        if DATA_FILE.exists():
            import shutil
            shutil.copy2(DATA_FILE, backup_path)
        
        # 保存新文件
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        # 更新全局变量
        data = new_data
        last_data_hash = new_hash
        
        sv.logger.info(f"✅ 半月刊数据更新成功！已加载 {len(data)} 条活动数据")
        return True
        
    except Exception as e:
        sv.logger.error(f"更新半月刊数据时出错: {str(e)}")
        return False

# 每小时检查更新的定时任务
@scheduler.scheduled_job('cron', hour='*')
async def auto_update_half_monthly():
    bot = get_bot()
    try:
        # 首次运行初始化哈希值
        global last_data_hash
        if last_data_hash is None and data:
            last_data_hash = calculate_data_hash(data)
        
        sv.logger.info("⏳ 开始自动检查半月刊更新...")
        has_update = await update_half_monthly_data()
        
        if has_update:
            sv.logger.info("🔔 检测到半月刊数据有更新，准备发送提醒...")
            
            # 获取所有群列表并发送消息
            gl = await bot.get_group_list()
            for g in gl:
                group_id = g['group_id']
                await bot.send_group_msg(
                    group_id=group_id,
                    message="🔔 半月刊数据已更新！\n可使用【半月刊】命令查看最新内容"
                )
        else:
            sv.logger.info("🔄 半月刊数据无更新")
            
    except Exception as e:
        sv.logger.error(f"自动更新半月刊时出错: {str(e)}")

# 修改原有的更新命令
@sv.on_command('更新半月刊', aliases=('更新数据', '刷新半月刊'))
async def update_half_monthly(session):
    try:
        if not priv.check_priv(session.event, priv.ADMIN):
            await session.send("⚠️ 需要管理员权限才能更新数据")
            return

        msg_id = (await session.send("⏳⏳⏳ 正在更新半月刊数据，请稍候..."))['message_id']
        
        has_update = await update_half_monthly_data()
        
        if has_update:
            await session.send("✅ 半月刊数据更新成功！\n"
                             f"已加载 {len(data)} 条活动数据\n"
                             "可以使用【半月刊】命令查看最新内容")
        else:
            await session.send("🔄 半月刊数据已是最新版本，无需更新")
            
    except Exception as e:
        sv.logger.error(f"更新半月刊数据时出错: {str(e)}")
        await session.send(f"❌❌ 更新过程中发生错误: {str(e)}")
    finally:
        if 'msg_id' in locals():
            try:
                await session.bot.delete_msg(message_id=msg_id)
            except:
                pass

# 活动分类颜色
category_colors = {
    "庆典活动": (255, 215, 0),
    "剧情活动": (100, 200, 255),
    "卡池": (255, 100, 100),
    "露娜塔": (200, 100, 255),
    "sp地下城": (150, 100, 200),
    "免费十连": (100, 255, 100),
    "公会战": (255, 150, 50),
    "新开专": (150, 200, 100),
    "斗技场": (200, 150, 100),
    "其他活动": (150, 150, 150)
}

# 活动分类函数
def classify_activity(activity_name):
    if 'N' in activity_name or 'H' in activity_name or 'VH' in activity_name or '庆典' in activity_name:
        return "庆典活动"
    elif '剧情活动' in activity_name or '角色活动' in activity_name or '活动' in activity_name:
        return "剧情活动"
    elif 'up' in activity_name or '卡池' in activity_name:
        return "卡池"
    elif '露娜塔' in activity_name:
        return "露娜塔"
    elif '免费十连' in activity_name:
        return "免费十连"
    elif '公会战' in activity_name:
        return "公会战"
    elif 'sp地下城' in activity_name:
        return "sp地下城"
    elif '新专1' in activity_name or '新专2' in activity_name:
        return "新开专"
    elif '斗技场' in activity_name or '斗技场开启' in activity_name:
        return "斗技场"
    else:
        return "其他活动"

# 格式化活动状态
def format_activity_status(start_time, end_time, current_time):
    duration = end_time - start_time
    duration_days = duration // (24 * 3600)
    duration_hours = (duration % (24 * 3600)) // 3600
    duration_str = f'{duration_days}天{duration_hours}小时' if duration_hours > 0 else f'{duration_days}天'
    
    if current_time < start_time:
        delta = start_time - current_time
        time_str = format_countdown(delta, is_future=True)
        return f'开始倒计时: {time_str}（持续{duration_str}）'
    else:
        delta = end_time - current_time
        if delta > 0:
            time_str = format_countdown(delta, is_future=False)
            return f'剩余时间: {time_str}'
        else:
            return f'已结束（持续{duration_str}）'

# 格式化倒计时
def format_countdown(seconds, is_future=True):
    total_seconds = seconds
    total_hours = total_seconds // 3600
    
    if total_hours >= 48:
        days = total_hours // 24
        remaining_seconds = total_seconds % (24 * 3600)
        hours = remaining_seconds // 3600
        remaining_seconds %= 3600
        minutes = remaining_seconds // 60
        return (
            f'{int(days)}天{int(hours)}时{int(minutes)}分' if is_future
            else f'{int(days)}天{int(hours)}时{int(minutes)}分'
        )
    else:
        hours = total_hours
        remaining_seconds = total_seconds % 3600
        minutes = remaining_seconds // 60
        
        if hours >= 24:
            days = hours // 24
            remaining_hours = hours % 24
            return (
                f'{int(days)}天{int(remaining_hours)}时{int(minutes)}分' if is_future
                else f'{int(days)}天{int(remaining_hours)}时{int(minutes)}分'
            )
        elif hours > 0:
            return (
                f'{int(hours)}时{int(minutes)}分' if is_future
                else f'{int(hours)}时{int(minutes)}分'
            )
        else:
            return (
                f'{int(minutes)}分' if is_future
                else f'{int(minutes)}分'
            )

# 绘制半月刊图片
async def draw_half_monthly_report():
    current_time = time.time()
    classified_activities = {
        "庆典活动": [],
        "剧情活动": [],
        "卡池": [],
        "露娜塔": [],
        "sp地下城": [],
        "免费十连": [],
        "公会战": [],
        "新开专": [],
        "斗技场": [],
        "其他活动": []
    }
    
    # 分类活动数据（保持不变）
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        if (start_time <= current_time <= end_time) or (start_time > current_time and (start_time - current_time) <= 15 * 24 * 3600):
            sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
            for sub in sub_activities:
                category = classify_activity(sub)
                time_status = format_activity_status(start_time, end_time, current_time)
                classified_activities[category].append(f"{time_status}\n{sub}")

    # 图片尺寸
    img_width = 800
    base_height = 180
    line_height = 35
    padding = 50
    
    # 计算内容高度（保持不变）
    content_height = 0
    for category, activities in classified_activities.items():
        if activities:
            content_height += 50  # 分类标题高度
            for activity in activities:
                lines = activity.split('\n')
                content_height += len([line for line in lines if line.strip()]) * line_height
                content_height += 10  # 行间距
            content_height += 20  # 分类间距
    
    total_height = base_height + content_height + padding * 2
    total_height = max(600, min(total_height, 3000))  # 限制最小和最大高度

    # 加载随机背景图片（修改为填充模式）
    bg_dir = "C:/Resources/img/benzi/"
    try:
        bg_files = [f for f in os.listdir(bg_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if bg_files:
            random_bg = random.choice(bg_files)
            bg_path = os.path.join(bg_dir, random_bg)
            bg_img = Image.open(bg_path).convert('RGBA')
            
            # 计算填充尺寸（保持宽高比）
            bg_width, bg_height = bg_img.size
            target_ratio = img_width / total_height
            bg_ratio = bg_width / bg_height
            
            if bg_ratio > target_ratio:
                # 按高度填充
                new_height = total_height
                new_width = int(bg_width * (new_height / bg_height))
            else:
                # 按宽度填充
                new_width = img_width
                new_height = int(bg_height * (new_width / bg_width))
            
            # 调整背景大小（保持宽高比）
            bg_img = bg_img.resize((new_width, new_height), Image.LANCZOS)
            
            # 创建画布并居中放置背景
            img = Image.new('RGBA', (img_width, total_height), (0, 0, 0, 0))
            x_offset = (img_width - new_width) // 2
            y_offset = (total_height - new_height) // 2
            img.paste(bg_img, (x_offset, y_offset))
            
            # 添加半透明遮罩使文字更清晰
            overlay = Image.new('RGBA', (img_width, total_height), (240, 240, 245, 180))
            img = Image.alpha_composite(img, overlay)
        else:
            # 无背景图片时使用纯色背景
            img = Image.new('RGB', (img_width, total_height), (240, 240, 245))
    except Exception as e:
        print(f"背景加载失败: {e}")
        # 出错时使用纯色背景
        img = Image.new('RGB', (img_width, total_height), (240, 240, 245))
    
    # 其余绘制代码保持不变...
    draw = ImageDraw.Draw(img)

    # 字体加载（保持不变）
    try:
        font_path = None
        for font_name in ["msyh.ttc", "simhei.ttf", "simsun.ttc", "Arial Unicode MS.ttf"]:
            try:
                font_path = ImageFont.truetype(font_name, 36)
                break
            except:
                continue
        
        if font_path is None:
            font_title = ImageFont.load_default()
            font_category = ImageFont.load_default()
            font_content = ImageFont.load_default()
        else:
            font_title = ImageFont.truetype(font_path.path, 36) if hasattr(font_path, 'path') else ImageFont.load_default()
            font_category = ImageFont.truetype(font_path.path, 28) if hasattr(font_path, 'path') else ImageFont.load_default()
            font_content = ImageFont.truetype(font_path.path, 24) if hasattr(font_path, 'path') else ImageFont.load_default()
    except Exception as e:
        print(f"字体加载失败: {e}")
        font_title = ImageFont.load_default()
        font_category = ImageFont.load_default()
        font_content = ImageFont.load_default()

    # 绘制标题（保持不变）
    title = "公主连结半月刊"
    try:
        title_width = draw.textlength(title, font=font_title)
        draw.text(((img_width - title_width) // 2, 50), title, fill=(0, 0, 0), font=font_title)
    except:
        draw.text((50, 50), title, fill=(0, 0, 0))

    # 绘制日期（保持不变）
    now = datetime.now()
    date_str = f"{now.year}年{now.month}月{now.day}日"
    try:
        date_width = draw.textlength(date_str, font=font_content)
        draw.text(((img_width - date_width) // 2, 100), date_str, fill=(100, 100, 100), font=font_content)
    except:
        draw.text((50, 100), date_str, fill=(100, 100, 100))

    # 绘制分割线（保持不变）
    draw.line([(50, 150), (img_width - 50, 150)], fill=(200, 200, 200), width=2)

    # 绘制活动内容（保持不变）
    y_position = 180
    
    for category, activities in classified_activities.items():
        if not activities:
            continue
            
        # 绘制分类标题
        draw.rectangle([(50, y_position), (img_width - 50, y_position + 40)], fill=category_colors[category])
        try:
            draw.text((70, y_position + 5), category, fill=(255, 255, 255), font=font_category)
        except:
            draw.text((70, y_position + 5), category, fill=(255, 255, 255))
        y_position += 50
        
        # 绘制活动内容
        for activity in activities:
            lines = activity.split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    try:
                        if i == 0 and ('开始倒计时' in line or '剩余时间' in line):
                            color = (255, 150, 50) if '开始倒计时' in line else (50, 200, 50)
                            draw.text((70, y_position), line, fill=color, font=font_content)
                        else:
                            draw.text((70, y_position), line, fill=(0, 0, 0), font=font_content)
                    except:
                        draw.text((70, y_position), line, fill=(0, 0, 0))
                    y_position += line_height
            y_position += 10
        
        y_position += 20 - 10  # 分类间距调整

    # 如果没有活动（保持不变）
    if y_position == 180:
        no_activity_text = "当前没有进行中和即将开始的活动"
        try:
            text_width = draw.textlength(no_activity_text, font=font_title)
            draw.text(((img_width - text_width) // 2, total_height // 2), no_activity_text, fill=(150, 150, 150), font=font_title)
        except:
            draw.text((50, total_height // 2), no_activity_text, fill=(150, 150, 150))

    # 保存图片（保持不变）
    img_byte_arr = io.BytesIO()
    if img.mode == 'RGBA':
        img = img.convert('RGB')
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr

@sv.on_command('半月刊')
async def half_monthly_report(session):
    img = await draw_half_monthly_report()
    await session.send("[CQ:image,file=base64://{}]".format(base64.b64encode(img.getvalue()).decode()))

# 通用绘制文本图片函数
async def draw_text_image(title, text):
    img_width = 800
    line_height = 40
    padding = 50
    title_height = 80
    text_lines = text.split('\n')
    content_height = len([line for line in text_lines if line.strip()]) * line_height
    total_height = title_height + content_height + padding * 2
    
    min_height = 300
    max_height = 2000
    total_height = max(min_height, min(total_height, max_height))
    
    background_color = (240, 240, 245)
    img = Image.new('RGB', (img_width, total_height), background_color)
    draw = ImageDraw.Draw(img)
    
    try:
        font_paths = [
            "msyh.ttc",
            "simhei.ttf",
            "simsun.ttc",
            "Arial Unicode MS.ttf"
        ]
        
        font_title = None
        font_content = None
        
        for path in font_paths:
            try:
                font_title = ImageFont.truetype(path, 36)
                font_content = ImageFont.truetype(path, 24)
                break
            except:
                continue
        
        if font_title is None:
            font_title = ImageFont.load_default()
            font_content = ImageFont.load_default()
    except:
        font_title = ImageFont.load_default()
        font_content = ImageFont.load_default()
    
    # 绘制标题
    title_width = draw.textlength(title, font=font_title)
    draw.text(((img_width - title_width) // 2, 30), title, fill=(0, 0, 0), font=font_title)
    
    # 绘制分割线
    draw.line([(50, 80), (img_width - 50, 80)], fill=(200, 200, 200), width=2)
    
    # 绘制文本内容
    y_position = 100
    for line in text_lines:
        if line.strip():
            # 为时间状态行添加颜色
            if ('开始倒计时' in line or '剩余时间' in line) and '[' in line and ']' in line:
                if '开始倒计时' in line:
                    color = (255, 150, 50)  # 橙色
                else:
                    color = (50, 200, 50)  # 绿色
                draw.text((padding, y_position), line, fill=color, font=font_content)
            else:
                draw.text((padding, y_position), line, fill=(0, 0, 0), font=font_content)
            y_position += line_height
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr

# 每日5:30自动发送日历
@scheduler.scheduled_job('cron', hour=5, minute=30)
async def daily_calendar():
    bot = get_bot()
    current_time = time.time()
    msg = '今日活动日历：\n'
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_end = today_start + 86400
    
    # 检查今日活动
    has_today_activity = False
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        if start_time <= current_time <= end_time:
            sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
            for sub in sub_activities:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
                has_today_activity = True
    
    if not has_today_activity:
        msg += '今日没有进行中的活动\n'
    
    # 检查今日即将开始的活动
    has_today_upcoming = False
    today_upcoming_msg = ''
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        
        if today_start <= start_time <= today_end and start_time > current_time:
            sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
            for sub in sub_activities:
                start_datetime = datetime.fromtimestamp(start_time)
                start_hour = start_datetime.hour
                start_minute = start_datetime.minute
                time_left = start_time - current_time
                hours_left = int(time_left // 3600)
                minutes_left = int((time_left % 3600) // 60)
                today_upcoming_msg += f'\n[今日{start_hour}:{start_minute:02d}开始] (还有{hours_left}小时{minutes_left}分钟)\n【{sub}】\n'
                has_today_upcoming = True
    
    if has_today_upcoming:
        msg += '\n今日即将开始的活动：' + today_upcoming_msg
    
    # 检查明天开始的活动
    tomorrow_start = today_start + 86400
    tomorrow_end = tomorrow_start + 86400
    
    has_tomorrow_activity = False
    tomorrow_msg = ''
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        
        if tomorrow_start <= start_time <= tomorrow_end:
            sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
            for sub in sub_activities:
                start_hour = datetime.fromtimestamp(start_time).hour
                tomorrow_msg += f'\n[明日{start_hour}点开始] \n【{sub}】\n'
                has_tomorrow_activity = True
    
    if has_tomorrow_activity:
        msg += '\n明日开始的活动：' + tomorrow_msg
    
    # 获取所有群列表并发送消息
    gl = await bot.get_group_list()
    for g in gl:
        group_id = g['group_id']
        img = await draw_text_image("今日活动日历", msg)
        await bot.send_group_msg(group_id=group_id, message=f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('日常活动', aliases=('日历', '日程'))
async def daily_activity(session):
    current_time = time.time()
    msg = '当前进行中的日常活动：\n'
    has_current_activity = False
    
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        if start_time <= current_time <= end_time:
            sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
            for sub in sub_activities:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
                has_current_activity = True
    
    if not has_current_activity:
        msg += '当前没有进行中的日常活动\n'
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_end = today_start + 86400
    
    has_today_upcoming = False
    today_upcoming_msg = ''
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        
        if today_start <= start_time <= today_end and start_time > current_time:
            sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
            for sub in sub_activities:
                start_datetime = datetime.fromtimestamp(start_time)
                start_hour = start_datetime.hour
                start_minute = start_datetime.minute
                time_left = start_time - current_time
                hours_left = int(time_left // 3600)
                minutes_left = int((time_left % 3600) // 60)
                today_upcoming_msg += f'\n[今日{start_hour}:{start_minute:02d}开始] (还有{hours_left}小时{minutes_left}分钟)\n【{sub}】\n'
                has_today_upcoming = True
    
    if has_today_upcoming:
        msg += '\n今日即将开始的活动：' + today_upcoming_msg
    
    tomorrow_start = today_start + 86400
    tomorrow_end = tomorrow_start + 86400
    
    has_tomorrow_activity = False
    tomorrow_msg = ''
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        
        if tomorrow_start <= start_time <= tomorrow_end:
            sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
            for sub in sub_activities:
                start_hour = datetime.fromtimestamp(start_time).hour
                tomorrow_msg += f'\n[明日{start_hour}点开始] \n【{sub}】\n'
                has_tomorrow_activity = True
    
    if has_tomorrow_activity:
        msg += '\n明日开始的活动：' + tomorrow_msg
    
    img = await draw_text_image("日常活动", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('剧情活动', aliases=('角色活动', '活动'))
async def story_activity(session):
    current_time = time.time()
    msg = '剧情活动（一周内活动）：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        if end_time <= current_time or (start_time - current_time) > 7 * 24 * 3600:
            continue
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if '活动' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('剧情活动（一周内活动）：\n') else msg + '当前没有剧情活动'
    img = await draw_text_image("剧情活动", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('up卡池', aliases=('up', '卡池'))
async def up_gacha(session):
    current_time = time.time()
    msg = 'up卡池（一周内活动）：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        if end_time <= current_time or (start_time - current_time) > 7 * 24 * 3600:
            continue
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if 'up' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('up卡池（一周内活动）：\n') else msg + '当前没有up卡池'
    img = await draw_text_image("UP卡池", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('免费十连')
async def free_gacha(session):
    current_time = time.time()
    msg = '免费十连活动：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if '免费十连' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('免费十连活动：\n') else msg + '当前没有免费十连活动'
    img = await draw_text_image("免费十连", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('公会战')
async def clan_battle(session):
    current_time = time.time()
    msg = '公会战信息：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if '公会战' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('公会战信息：\n') else msg + '当前没有公会战活动'
    img = await draw_text_image("公会战", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('露娜塔')
async def luna_tower(session):
    current_time = time.time()
    msg = '露娜塔信息：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if '露娜塔' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('露娜塔信息：\n') else msg + '当前没有露娜塔活动'
    img = await draw_text_image("露娜塔", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('新开专')
async def new_unique(session):
    current_time = time.time()
    msg = '新开专武信息：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if '新专1' in sub or '新专2' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('新开专武信息：\n') else msg + '当前没有新开专武信息'
    img = await draw_text_image("新开专武", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('斗技场')
async def arena(session):
    current_time = time.time()
    msg = '斗技场信息：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if '斗技场' in sub or '竞技场' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('斗技场信息：\n') else msg + '当前没有斗技场活动'
    img = await draw_text_image("斗技场", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('庆典活动', aliases=('庆典'))
async def campaign(session):
    current_time = time.time()
    msg = '庆典/双倍活动：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if 'N' in sub or 'H' in sub or 'VH' in sub or '庆典' in sub or '双倍' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('庆典/双倍活动：\n') else msg + '当前没有庆典/双倍活动'
    img = await draw_text_image("庆典活动", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

@sv.on_command('地下城', aliases=('sp地下城', '地下城活动'))
async def dungeon(session):
    current_time = time.time()
    msg = '地下城活动：\n'
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        sub_activities = re.findall(r'【(.*?)】', activity['活动名'])
        for sub in sub_activities:
            if 'sp地下城' in sub:
                time_status = format_activity_status(start_time, end_time, current_time)
                msg += f'\n[{time_status}] \n【{sub}】\n'
    
    msg = msg if len(msg) > len('地下城活动：\n') else msg + '当前没有地下城活动'
    img = await draw_text_image("地下城活动", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")
