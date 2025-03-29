import datetime
import os
import re
import shutil
import sqlite3 as db


home_directory = os.path.expanduser("~")
bear_path = home_directory + \
    "/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/"
sqlite_file = bear_path + "database.sqlite"
note_files_dir = bear_path + "Local Files/"
note_table_name = "ZSFNOTE"
bear_dir = "bear/"
output_dir = "/Users/charliec/Downloads/"
resource_dir = "resources/"
bear_total_dir = output_dir + bear_dir
resource_total_dir = output_dir + bear_dir + resource_dir


def read_sqlite(db_path, exectCmd):
    conn = db.connect(db_path)
    cursor = conn.cursor()
    conn.row_factory = db.Row
    cursor.execute(exectCmd)
    rows = cursor.fetchall()
    return rows


def save_to_file(file_name, content):
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(content)
        f.close()


def list_all_files(directory):
    all_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            all_files.append(os.path.join(root, file))
    return all_files


def export():
    all_files = list_all_files(note_files_dir)
    file_pattern = r'\[.*\]\(.*\)'

    notes = read_sqlite(
        sqlite_file, "SELECT ZTITLE, ZSUBTITLE, ZTEXT, ZCREATIONDATE, ZMODIFICATIONDATE, ZTRASHED, ZTRASHEDDATE FROM " + note_table_name + ";")

    for note in notes:
        create_time = datetime.datetime.fromtimestamp(
            float(note[3])).strftime("%Y-%m-%d %H:%M:%S")
        modify_time = datetime.datetime.fromtimestamp(
            float(note[4])).strftime("%Y-%m-%d %H:%M:%S")
        trash_time = datetime.datetime.fromtimestamp(
            float(note[5])).strftime("%Y-%m-%d %H:%M:%S")

        title = note[0]
        if title == "":
            title = note[1]
        if title == "":
            title = "未命名" + create_time
        title = title.replace("/", "|")

        content = note[2]
        # 确保content是字符串类型
        if content is None:
            content = ""
        content = str(content)
        is_trashed = note[5]

        print("笔记：" + title + "，是否在废纸篓：" + str(is_trashed == 1))

        # 时间还不准
        # content += "\n\n编辑日期：" + modify_time
        # content += "\n创建日期：" + create_time
        # if is_trashed:
        #     content += "\n回收日期：" + trash_time

        matches = re.findall(file_pattern, content)
        for match in matches:
            left_index = match.index("(") + 1
            file_name = match[left_index:-1]
            for file in all_files:
                if file_name in file:
                    # 只使用文件名，不包含路径
                    file_name_only = os.path.basename(file_name)
                    shutil.copy(file, resource_total_dir + file_name_only)
                    content = content.replace(
                        file_name, resource_dir + file_name_only)
                    break

        save_to_file(bear_total_dir + title + ".md", content)


def check():
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not os.path.exists(bear_total_dir):
        os.makedirs(bear_total_dir)
    if not os.path.exists(resource_total_dir):
        os.makedirs(resource_total_dir)


check()
export()
