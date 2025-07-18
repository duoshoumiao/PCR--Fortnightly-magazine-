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
from io import BytesIO  
import asyncio  # 添加这行导入
import json
from pathlib import Path
from nonebot import on_command, get_bot
from nonebot import scheduler
import pytz
import requests
import hoshino
from hoshino import R, Service, priv, util
from hoshino.typing import CQEvent
from hoshino.service import Service as sv  # 关键修复点

sv = SafeService('半月刊', enable_on_default=False, bundle='半月刊', help_='''
【半月刊】：完整图片版\n
【日常活动|日历|日程】：显示进行中的活动和明天开始的活动\n
【剧情活动|角色活动|活动】：只显示角色剧情活动\n
【up卡池|up|卡池】：显示当前卡池跟未来卡池\n
【免费十连】 - 免费十连活动
【公会战】- 公会战信息
【露娜塔】 - 露娜塔信息
【新开专】 - 新开专武信息
【斗技场】 - 斗技场信息
【庆典活动】 - 庆典和双倍活动
【sp地下城】 - sp地下城
【开启每日推送】 - 开启每日5:30的活动推送
【关闭每日推送】 - 关闭每日推送
【更新半月刊】
'''.strip())
 

# ========== 配置文件管理 ==========
PUSH_CONFIG_PATH = Path(__file__).parent / "push_config.json"

class PushConfig:
    @staticmethod
    def load():
        """加载推送配置"""
        try:
            if PUSH_CONFIG_PATH.exists():
                with open(PUSH_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            sv.logger.error(f"加载推送配置失败: {e}")
            return {}

    @staticmethod
    def save(config):
        """保存推送配置"""
        try:
            with open(PUSH_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            sv.logger.error(f"保存推送配置失败: {e}")

    @staticmethod
    def set_group(group_id, enabled):
        """设置群组推送状态"""
        config = PushConfig.load()
        config[str(group_id)] = enabled
        PushConfig.save(config)

    @staticmethod
    def get_group(group_id):
        """获取群组推送状态"""
        config = PushConfig.load()
        return config.get(str(group_id), False)

    @staticmethod
    def get_all_enabled():
        """获取所有开启推送的群"""
        config = PushConfig.load()
        return [int(gid) for gid, enabled in config.items() if enabled]

# ========== 命令处理 ==========
@sv.on_command('开启每日推送')
async def enable_daily_push(session):
    """开启本群每日推送"""
    if not priv.check_priv(session.event, priv.ADMIN):
        await session.send("⚠️ 需要管理员权限")
        return
    
    group_id = session.event.group_id
    PushConfig.set_group(group_id, True)
    await session.send("✅ 已开启本群每日5:30的活动推送")

@sv.on_command('关闭每日推送')
async def disable_daily_push(session):
    """关闭本群每日推送"""
    if not priv.check_priv(session.event, priv.ADMIN):
        await session.send("⚠️ 需要管理员权限")
        return
    
    group_id = session.event.group_id
    PushConfig.set_group(group_id, False)
    await session.send("✅ 已关闭本群每日活动推送")

# ========== 定时推送任务 ==========
@scheduler.scheduled_job('cron', hour=5, minute=30)
async def daily_calendar_push():
    """每日5:30自动推送"""
    bot = get_bot()
    enabled_groups = PushConfig.get_all_enabled()
    
    if not enabled_groups:
        sv.logger.info("当前没有群组开启每日推送")
        return
    
    try:
        # 获取日常活动文本内容
        msg = await get_daily_activity_text()
        # 生成图片 - 修改这里
        img = await draw_text_image_with_icons("每日活动推送", msg)
        img_b64 = base64.b64encode(img.getvalue()).decode()
        
        for group_id in enabled_groups:
            try:
                await bot.send_group_msg(
                    group_id=group_id,
                    message=f"[CQ:image,file=base64://{img_b64}]"
                )
                sv.logger.info(f"已向群 {group_id} 发送每日推送")
            except Exception as e:
                sv.logger.error(f"群 {group_id} 推送失败: {e}")
    except Exception as e:
        sv.logger.error(f"生成推送图片失败: {e}")

async def get_daily_activity_text():
    """获取日常活动文本内容"""
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
    
    return msg

# ========== 工具函数 ==========
def format_activity_status(start_time, end_time, current_time):
    """格式化活动状态"""
    duration = end_time - start_time
    duration_days = duration // (24 * 3600)
    duration_hours = (duration % (24 * 3600)) // 3600
    
    # 计算持续时间的字符串表示
    if duration_hours > 0:
        duration_str = f'{duration_days}天{duration_hours}小时'
    else:
        duration_str = f'{duration_days}天'
    
    # 获取开始日期的日部分
    start_date = datetime.fromtimestamp(start_time)
    start_day = start_date.day
    
    if current_time < start_time:
        delta = start_time - current_time
        time_str = format_countdown(delta, is_future=True)
        # 修改这里：在持续天数前增加开始日期
        return f'开始倒计时: {time_str}（{start_day}号开始,持续{duration_str}）'
    else:
        delta = end_time - current_time
        if delta > 0:
            time_str = format_countdown(delta, is_future=False)
            return f'剩余时间: {time_str}'
        else:
            return f'已结束（持续{duration_str}）'

def format_countdown(seconds, is_future=True):
    """格式化倒计时"""
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

# 获取 data.json 的绝对路径
DATA_FILE = Path(__file__).parent / "data.json"

def load_activity_data():
    # 检查文件是否存在
    if not DATA_FILE.exists():
        sv.logger.error(f"❌❌ data.json 文件不存在！路径：{DATA_FILE}")
        return []

    # 检查文件是否可读
    if not os.access(DATA_FILE, os.R_OK):
        sv.logger.error(f"❌❌ data.json 不可读！请检查权限。")
        return []

    # 尝试读取 JSON
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            sv.logger.info("✅ 成功加载 data.json")
            return data
    except json.JSONDecodeError as e:
        sv.logger.error(f"❌❌ data.json 格式错误: {e}")
        return []
    except Exception as e:
        sv.logger.error(f"❌❌ 无法读取 data.json: {e}")
        return []

# 加载数据
data = load_activity_data()

if not data:
    sv.logger.error("⚠️ 活动数据为空，请检查 data.json！")
else:
    sv.logger.info(f"📊📊 已加载 {len(data)} 条活动数据")

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

# 每小时检查更新的定时任务（不发送通知）
@scheduler.scheduled_job('cron', hour='*')
async def auto_update_half_monthly():
    try:
        # 首次运行初始化哈希值
        global last_data_hash
        if last_data_hash is None and data:
            last_data_hash = calculate_data_hash(data)
        
        sv.logger.info("⏳⏳⏳⏳⏳⏳⏳⏳⏳ 开始自动检查半月刊更新...")
        has_update = await update_half_monthly_data()
        
        if has_update:
            sv.logger.info("🔔🔔🔔🔔 检测到半月刊数据有更新")
        else:
            sv.logger.info("🔄🔄🔄🔄 半月刊数据无更新")
            
    except Exception as e:
        sv.logger.error(f"自动更新半月刊时出错: {str(e)}")

# 修改原有的更新命令
@sv.on_command('更新半月刊', aliases=('更新数据', '刷新半月刊'))
async def update_half_monthly(session):
    try:
        if not priv.check_priv(session.event, priv.ADMIN):
            await session.send("⚠️ 需要管理员权限才能更新数据")
            return

        msg_id = (await session.send("⏳⏳⏳⏳⏳⏳⏳⏳⏳ 正在更新半月刊数据，请稍候..."))['message_id']
        
        has_update = await update_half_monthly_data()
        
        if has_update:
            await session.send("✅ 半月刊数据更新成功！\n"
                             f"已加载 {len(data)} 条活动数据\n"
                             "可以使用【半月刊】命令查看最新内容")
        else:
            await session.send("🔄🔄 半月刊数据已是最新版本，无需更新")
            
    except Exception as e:
        sv.logger.error(f"更新半月刊数据时出错: {str(e)}")
        await session.send(f"❌❌❌❌ 更新过程中发生错误: {str(e)}")
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

# 绘制半月刊图片
# 修改绘制半月刊图片的函数
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

    # 分类活动数据
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
    img_width = 1400
    base_height = 180
    line_height = 35
    icon_size = 50
    icon_line_height = 40
    padding = 50
    
    # 计算总行数
    total_lines = 0
    category_blocks = []
    for category, activities in classified_activities.items():
        if activities:
            block_lines = 1 + len(activities) * 3 + 1
            total_lines += block_lines
            block_height = 50 + (len(activities) * (line_height * 2 + icon_line_height + 15))
            category_blocks.append((category, activities, block_height))
    
    # 自动切换双列模式
    use_two_columns = total_lines > 30

    # 分配内容到列
    column_heights = [0, 0]
    column_contents = [[], []]
    
    for block in category_blocks:
        if use_two_columns:
            target_col = 0 if column_heights[0] <= column_heights[1] else 1
            column_contents[target_col].append(block)
            column_heights[target_col] += block[2] + 20
        else:
            column_contents[0].append(block)

    # 计算总高度
    content_height = max(column_heights) if use_two_columns else sum(block[2] + 20 for block in category_blocks)
    total_height = base_height + content_height + padding * 2
    total_height = max(600, min(total_height, 3000))

    # 创建画布
    try:
        bg_dir = "C:/Resources/img/benzi/"
        bg_files = [f for f in os.listdir(bg_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if bg_files:
            random_bg = random.choice(bg_files)
            bg_img = Image.open(os.path.join(bg_dir, random_bg)).convert('RGBA')
            
            bg_width, bg_height = bg_img.size
            target_ratio = img_width / total_height
            bg_ratio = bg_width / bg_height
            
            if bg_ratio > target_ratio:
                new_height = total_height
                new_width = int(bg_width * (new_height / bg_height))
            else:
                new_width = img_width
                new_height = int(bg_height * (new_width / bg_width))
            
            bg_img = bg_img.resize((new_width, new_height), Image.LANCZOS)
            
            img = Image.new('RGBA', (img_width, total_height), (0, 0, 0, 0))
            x_offset = (img_width - new_width) // 2
            y_offset = (total_height - new_height) // 2
            img.paste(bg_img, (x_offset, y_offset))
            
            overlay = Image.new('RGBA', (img_width, total_height), (240, 240, 245, 180))
            img = Image.alpha_composite(img, overlay)
        else:
            img = Image.new('RGB', (img_width, total_height), (240, 240, 245))
    except Exception as e:
        sv.logger.error(f"背景加载失败: {e}")
        img = Image.new('RGB', (img_width, total_height), (240, 240, 245))
    
    draw = ImageDraw.Draw(img)

    # 加载字体
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
        sv.logger.error(f"字体加载失败: {e}")
        font_title = ImageFont.load_default()
        font_category = ImageFont.load_default()
        font_content = ImageFont.load_default()

    # 绘制标题 - 去掉描边
    title = "公主连结半月刊"
    try:
        title_width = draw.textlength(title, font=font_title)
        draw.text(((img_width - title_width) // 2, 50), title, fill=(0, 0, 0), font=font_title)
    except:
        draw.text((50, 50), title, fill=(0, 0, 0))

    # 绘制日期 - 保留描边
    now = datetime.now()
    date_str = f"{now.year}年{now.month}月{now.day}日"
    try:
        date_width = draw.textlength(date_str, font=font_content)
        x, y = (img_width - date_width) // 2, 100
        
        # 绘制描边（使用深灰色）
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    draw.text((x+dx, y+dy), date_str, fill=(80, 80, 80), font=font_content)
        
        # 绘制主文字
        draw.text((x, y), date_str, fill=(100, 100, 100), font=font_content)
    except:
        x, y = 50, 100
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    draw.text((x+dx, y+dy), date_str, fill=(80, 80, 80))
        draw.text((x, y), date_str, fill=(100, 100, 100))

    # 绘制分割线
    draw.line([(50, 150), (img_width - 50, 150)], fill=(200, 200, 200), width=2)

    # 绘制内容区域
    y_start = 180
    column_width = img_width // 2 - 70 if use_two_columns else img_width - 100
    
    async def process_char_ids(text, x, y):
        """处理文本中的角色ID，返回处理后的文本和头像列表"""
        char_ids = re.findall(r'\d{4,6}', text)
        icons = []
        
        for char_id in char_ids:
            try:
                char_icon_path = R.img(f'priconne/unit/icon_unit_{char_id}31.png').path
                if os.path.exists(char_icon_path):
                    icon = Image.open(char_icon_path).convert("RGBA")
                    icon = icon.resize((icon_size, icon_size), Image.LANCZOS)
                    
                    # 为头像添加白色边框
                    border_size = 2
                    bordered_icon = Image.new('RGBA', (icon_size + border_size*2, icon_size + border_size*2), (255, 255, 255, 200))
                    bordered_icon.paste(icon, (border_size, border_size), icon)
                    
                    icons.append((char_id, bordered_icon))
                    text = text.replace(char_id, "")
            except Exception as e:
                sv.logger.error(f"加载角色头像失败: {e}")
                text = text.replace(char_id, "")
        
        return text, icons
    
    async def draw_column(x_offset, blocks):
        """异步绘制列内容"""
        nonlocal img, draw
        y = y_start
        
        for category, activities, block_height in blocks:
            # 绘制分类标题 - 添加半透明白色边框
            border_color = (255, 255, 255, 180)  # 半透明白色
            fill_color = (*category_colors[category], 220)  # 增加透明度
            
            # 绘制边框
            border_width = 3
            draw.rounded_rectangle(
                [(x_offset-border_width, y-border_width), 
                 (x_offset + column_width + border_width, y + 40 + border_width)],
                radius=10, fill=border_color
            )
            
            # 绘制分类背景
            draw.rounded_rectangle(
                [(x_offset, y), (x_offset + column_width, y + 40)],
                radius=10, fill=fill_color
            )
            
            # 绘制分类标题文字 - 添加同色系较深描边
            try:
                text = category
                text_width = draw.textlength(text, font=font_category)
                text_x = x_offset + (column_width - text_width) // 2
                text_y = y + 5
                
                # 计算同色系较深颜色
                r, g, b = category_colors[category]
                outline_color = (max(0, r-60), max(0, g-60), max(0, b-60))
                
                # 绘制描边
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx != 0 or dy != 0:
                            draw.text((text_x+dx, text_y+dy), text, fill=outline_color, font=font_category)
                
                # 绘制主文字
                draw.text((text_x, text_y), text, fill=(255, 255, 255), font=font_category)
            except:
                draw.text((x_offset + 20, y + 5), category, fill=(255, 255, 255))
            
            y += 50
            
            # 绘制活动内容 - 添加半透明白色背景
            for activity in activities:
                lines = activity.split('\n')
                icons_list = []
                
                # 处理文本并收集头像
                processed_lines = []
                for line in lines:
                    processed_line, icons = await process_char_ids(line, x_offset + 20, y)
                    processed_lines.append(processed_line)
                    icons_list.append(icons)
                
                # 为活动内容添加半透明背景
                content_height = len(processed_lines) * line_height
                if any(icons_list):
                    content_height += icon_line_height
                
                content_bg = Image.new('RGBA', (column_width, content_height + 20), (255, 255, 255, 100))
                img.paste(content_bg, (x_offset, y), content_bg)
                
                # 绘制文本 - 倒计时使用同色系较深描边
                for i, line in enumerate(processed_lines):
                    if line.strip():
                        # 确定颜色
                        if i == 0 and '开始倒计时' in line:
                            main_color = (255, 200, 50)  # 亮橙色
                            outline_color = (180, 120, 0)  # 深橙色描边
                        elif i == 0 and '剩余时间' in line:
                            main_color = (100, 255, 100)  # 亮绿色
                            outline_color = (0, 150, 0)  # 深绿色描边
                        else:
                            main_color = (0, 0, 0)       # 黑色
                            outline_color = None
                        
                        # 绘制倒计时文本的描边
                        if i == 0 and outline_color:  # 只有倒计时文本添加描边
                            for dx in [-1, 0, 1]:
                                for dy in [-1, 0, 1]:
                                    if dx != 0 or dy != 0:
                                        draw.text((x_offset + 20 + dx, y + dy), line, 
                                                 fill=outline_color, font=font_content)
                        
                        # 绘制主文字
                        draw.text((x_offset + 20, y), line, fill=main_color, font=font_content)
                        y += line_height
                
                # 绘制头像行
                if any(icons_list):
                    x_icon = x_offset + 20
                    y_icon = y
                    
                    # 合并所有头像
                    all_icons = []
                    for icons in icons_list:
                        all_icons.extend(icons)
                    
                    # 绘制头像
                    for char_id, icon in all_icons:
                        img.paste(icon, (x_icon, y_icon), icon)
                        x_icon += icon_size + 5
                    
                    y += icon_line_height
                else:
                    y += 15
                
                y += 15
            
            y += 15

    # 根据模式绘制内容
    if use_two_columns:
        await draw_column(50, column_contents[0])
        await draw_column(img_width // 2 + 20, column_contents[1])
    else:
        await draw_column(50, column_contents[0])

    # 如果没有活动
    if not any(activities for _, activities in classified_activities.items()):
        no_activity_text = "当前没有进行中和即将开始的活动"
        try:
            text_width = draw.textlength(no_activity_text, font=font_title)
            draw.text(((img_width - text_width) // 2, total_height // 2), no_activity_text, fill=(150, 150, 150), font=font_title)
        except:
            draw.text((50, total_height // 2), no_activity_text, fill=(150, 150, 150))

    # 保存图片
    img_byte_arr = io.BytesIO()
    if img.mode == 'RGBA':
        img = img.convert('RGB')
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr

@sv.on_command('半月刊')
async def half_monthly_report(session):
    # 先发送一条提示消息
    msg_id = (await session.send("⏳ 半月刊生成中，请稍等..."))['message_id']
    
    try:
        # 生成图片
        img = await draw_half_monthly_report()
        # 发送图片
        await session.send("[CQ:image,file=base64://{}]".format(base64.b64encode(img.getvalue()).decode()))
    except Exception as e:
        sv.logger.error(f"生成半月刊时出错: {e}")
        await session.send("❌ 生成半月刊时出错，请稍后再试")
    finally:
        # 尝试删除提示消息
        try:
            await session.bot.delete_msg(message_id=msg_id)
        except Exception as e:
            sv.logger.error(f"删除提示消息失败: {e}")

# 通用绘制文本图片函数
async def draw_text_image_with_icons(title: str, content: str):
    """绘制带标题和头像的文本图片（头像显示在对应内容的下一行）"""
    # 图片尺寸
    img_width = 800
    line_height = 40
    icon_size = 50
    icon_padding = 5
    padding = 40
    
    # 分割内容为段落
    paragraphs = content.split('\n\n')
    
    # 计算所需高度
    total_height = padding * 2 + 60  # 基础高度（标题区域）
    
    # 预计算所有段落和头像
    paragraph_data = []
    for para in paragraphs:
        # 处理角色ID
        char_ids = re.findall(r'\d{4,6}', para)
        icons = []
        processed_text = para
        
        for char_id in char_ids:
            try:
                char_icon_path = R.img(f'priconne/unit/icon_unit_{char_id}31.png').path
                if os.path.exists(char_icon_path):
                    icon = Image.open(char_icon_path).convert("RGBA")
                    icon = icon.resize((icon_size, icon_size), Image.LANCZOS)
                    
                    # 为头像添加白色边框
                    border_size = 2
                    bordered_icon = Image.new('RGBA', (icon_size + border_size*2, icon_size + border_size*2), (255, 255, 255, 200))
                    bordered_icon.paste(icon, (border_size, border_size), icon)
                    
                    icons.append(bordered_icon)
                    processed_text = processed_text.replace(char_id, "")
            except Exception as e:
                sv.logger.error(f"加载角色头像失败: {e}")
                processed_text = processed_text.replace(char_id, "")
        
        # 计算段落高度
        lines = processed_text.split('\n')
        text_height = len(lines) * line_height
        if icons:
            text_height += icon_size + 10  # 头像行高度
        
        paragraph_data.append({
            'text': processed_text,
            'icons': icons,
            'height': text_height
        })
        total_height += text_height + 20  # 段落间距
    
    # 创建图片
    img = Image.new('RGB', (img_width, total_height), (240, 240, 245))
    draw = ImageDraw.Draw(img)
    
    # 加载字体
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
            font_content = ImageFont.load_default()
        else:
            font_title = ImageFont.truetype(font_path.path, 36) if hasattr(font_path, 'path') else ImageFont.load_default()
            font_content = ImageFont.truetype(font_path.path, 24) if hasattr(font_path, 'path') else ImageFont.load_default()
    except Exception as e:
        print(f"字体加载失败: {e}")
        font_title = ImageFont.load_default()
        font_content = ImageFont.load_default()
    
    # 绘制标题
    try:
        title_width = draw.textlength(title, font=font_title)
        draw.text(((img_width - title_width) // 2, padding), title, fill=(0, 0, 0), font=font_title)
    except:
        draw.text((padding, padding), title, fill=(0, 0, 0))
    
    # 绘制分割线
    draw.line([(padding, padding + 50), (img_width - padding, padding + 50)], fill=(200, 200, 200), width=2)
    
    # 绘制内容
    y_position = padding + 60
    
    for para in paragraph_data:
        # 绘制文本
        lines = para['text'].split('\n')
        for line in lines:
            if line.strip():
                try:
                    draw.text((padding, y_position), line, fill=(0, 0, 0), font=font_content)
                except:
                    draw.text((padding, y_position), line, fill=(0, 0, 0))
                y_position += line_height
        
        # 绘制头像（在文本下方）
        if para['icons']:
            x_icon = padding
            for icon in para['icons']:
                img.paste(icon, (x_icon, y_position), icon)
                x_icon += icon_size + icon_padding
            y_position += icon_size + 10
        
        y_position += 10  # 段落间距
    
    # 保存图片
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr


async def daily_activity():
    """日常活动"""
    current_time = time.time()
    msg = ""
    
    for activity in data:
        start_time = datetime.strptime(activity['开始时间'], "%Y/%m/%d %H").timestamp()
        end_time = datetime.strptime(activity['结束时间'], "%Y/%m/%d %H").timestamp()
        
        if start_time <= current_time <= end_time:
            time_status = format_activity_status(start_time, end_time, current_time)
            msg += f"{time_status}\n{activity['活动名']}\n\n"
    
    if not msg:
        msg = "当前没有进行中的活动"
    
    img = await draw_text_image("日常活动", msg)
    return img

# 日常活动/日历功能
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
    
    img = await draw_text_image_with_icons("日常活动", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# 剧情活动功能
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
    img = await draw_text_image_with_icons("剧情活动", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# UP卡池功能
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
    img = await draw_text_image_with_icons("UP卡池", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# 免费十连功能
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
    img = await draw_text_image_with_icons("免费十连", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# 公会战功能
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
    img = await draw_text_image_with_icons("公会战", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# 露娜塔功能
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
    img = await draw_text_image_with_icons("露娜塔", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# 新开专武功能
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
    img = await draw_text_image_with_icons("新开专武", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# 斗技场功能
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
    img = await draw_text_image_with_icons("斗技场", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# 庆典活动功能
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
    img = await draw_text_image_with_icons("庆典活动", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")

# 地下城功能
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
    img = await draw_text_image_with_icons("地下城活动", msg)
    await session.send(f"[CQ:image,file=base64://{base64.b64encode(img.getvalue()).decode()}]")
    
