#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学生名单导入工具（零第三方依赖，Python 3.8+）

从 Excel/CSV 识别学生信息并导入运行中的报考系统。真实名单只通过服务端接口写入
加密的 data/seasons/<季>.json，绝不写入 public/ 静态目录、绝不生成本地明文副本。

用法（在 src/ 目录下执行）：
    python tools/import-roster.py -f 名单.xlsx                 # 只预览，不写入
    python tools/import-roster.py -f 名单.xlsx --sheet "Sheet1"
    python tools/import-roster.py -f 名单.xlsx --map dob=出生年月 --commit
    EXAM_ADMIN_PASS='你的口令' python tools/import-roster.py -f 名单.xlsx --commit --yes

默认 dry-run：只打印字段映射、统计和脱敏预览。加 --commit 才会写入。
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from urllib import request
from urllib.error import URLError, HTTPError

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

# 表头同义词：规范化后做匹配，支持乱序、多余列、中英文混用
ALIASES = {
    "id":  ["学号", "学生编号", "学籍号", "考生号", "考号", "学生号", "编号", "studentid",
            "studentno", "studentnumber", "student id", "sno", "id"],
    "cls": ["班级", "行政班", "所在班级", "年级班级", "班别", "教学班", "class", "classname",
            "gradeclass", "班"],
    "cn":  ["中文名", "中文姓名", "姓名", "学生姓名", "姓名中文", "chinesename", "namecn",
            "studentname", "name"],
    "en":  ["姓名大写", "大写拼音", "姓名拼音", "拼音", "英文姓名", "护照姓名", "姓名拼音大写",
            "englishname", "nameincapitals", "nameinenglish", "pinyin", "nameen", "enname"],
    "g":   ["性别", "gender", "sex"],
    "dob": ["出生日期", "出生年月日", "出生年月", "生日", "出生日", "dateofbirth", "dob",
            "birthdate", "birthday", "birth date"],
}
FIELD_CN = {"id": "学号", "cls": "班级", "cn": "中文姓名", "en": "姓名大写", "g": "性别", "dob": "出生日期"}
REQUIRED = ("cls", "cn", "dob")


# ------------------------- 读取表格 -------------------------
def col_index(ref):
    m = re.match(r"([A-Za-z]+)", ref or "")
    if not m:
        return -1
    n = 0
    for ch in m.group(1).upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx(path, sheet_name=None):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))

        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
                rels[rel.get("Id")] = rel.get("Target")

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = []
        for sh in wb.find(NS + "sheets"):
            target = rels.get(sh.get(RID), "") or ""
            if target.startswith("/"):
                p = target.lstrip("/")
            elif target.startswith("xl/"):
                p = target
            else:
                p = "xl/" + target.lstrip("/")
            if p in names:
                sheets.append((sh.get("name"), p))
        if not sheets:
            # 回退：直接找 worksheets 下的第一个 sheet
            cand = sorted(n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            if not cand:
                raise ValueError("未在 xlsx 中找到工作表")
            sheets = [("(默认)", cand[0])]

        target = None
        if sheet_name:
            for n, p in sheets:
                if n == sheet_name:
                    target = p
                    break
            if not target:
                raise ValueError("找不到工作表 %r，可用：%s" % (sheet_name, "、".join(n for n, _ in sheets)))
        else:
            target = sheets[0][1]

        root = ET.fromstring(z.read(target))
        rows = []
        for row in root.iter(NS + "row"):
            cells = {}
            for c in row.findall(NS + "c"):
                ref, typ = c.get("r") or "", c.get("t")
                v = c.find(NS + "v")
                if typ == "inlineStr":
                    is_ = c.find(NS + "is")
                    val = "".join(t.text or "" for t in is_.iter(NS + "t")) if is_ is not None else ""
                elif v is None:
                    val = ""
                elif typ == "s":
                    try:
                        val = shared[int(v.text)]
                    except (ValueError, IndexError):
                        val = ""
                elif typ == "b":
                    val = "TRUE" if v.text == "1" else "FALSE"
                else:
                    val = v.text or ""
                ci = col_index(ref)
                if ci < 0:
                    ci = len(cells)
                cells[ci] = val
            width = max(cells) + 1 if cells else 0
            rows.append([cells.get(i, "") for i in range(width)])
        return rows, [n for n, _ in sheets]


def read_csv_rows(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV 编码无法识别，请另存为 UTF-8")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)]


# ------------------------- 字段识别 -------------------------
def norm_header(s):
    s = str(s or "").strip().lower()
    return re.sub(r"[\s_\-—()（）\[\]【】:：/\\、,，.。*#]", "", s)


def guess_fields(header_row):
    keys = [norm_header(x) for x in header_row]
    cand = []
    for ci, key in enumerate(keys):
        if not key:
            continue
        for field, aliases in ALIASES.items():
            best = 0
            for a in aliases:
                a = norm_header(a)
                if not a:
                    continue
                if key == a:
                    best = max(best, 100)
                elif len(a) >= 2 and (key.startswith(a) or key.endswith(a) or a in key):
                    best = max(best, 60 + len(a))
                elif len(key) >= 2 and key in a:
                    best = max(best, 40 + len(key))
            if best >= 60:
                cand.append((best, ci, field))
    cand.sort(key=lambda x: (-x[0], x[1]))
    mapping, used_cols, used_fields = {}, set(), set()
    for _, ci, field in cand:
        if ci in used_cols or field in used_fields:
            continue
        mapping[field] = ci
        used_cols.add(ci)
        used_fields.add(field)
    return mapping


def detect_header(rows):
    best = (-1, 0, {})
    for i, row in enumerate(rows[:10]):
        m = guess_fields(row)
        score = len(m) + 3 * sum(1 for f in REQUIRED if f in m)
        if score > best[0]:
            best = (score, i, m)
    return best[1], best[2]


# ------------------------- 值规范化 -------------------------
def excel_serial(v):
    try:
        n = float(v)
    except ValueError:
        return ""
    if not (10000 <= n <= 80000):
        return ""
    # Excel 1900 日期系统（含 1900 闰年 bug），基准取 1899-12-30
    return (date(1899, 12, 30) + timedelta(days=int(n))).isoformat()


def norm_dob(v):
    s = str(v or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        d = excel_serial(s)
        if d:
            return d
    if re.fullmatch(r"\d{8}", s):
        s = s[:4] + "-" + s[4:6] + "-" + s[6:]
    m = re.match(r"^(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", s)
    if not m:
        return ""
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return ""


def norm_gender(v):
    s = str(v or "").strip().lower()
    if s in ("男", "m", "male", "boy", "1"):
        return "男"
    if s in ("女", "f", "female", "girl", "0"):
        return "女"
    return str(v or "").strip()


def build_students(rows, hi, mapping):
    width = max(mapping.values()) + 1 if mapping else 0
    students, issues = [], []
    for ri in range(hi + 1, len(rows)):
        row = list(rows[ri]) + [""] * max(0, width - len(rows[ri]))

        def g(f):
            return str(row[mapping[f]] if f in mapping else "").strip()

        cn, cls, dob = g("cn"), g("cls"), norm_dob(g("dob"))
        if not (cn or cls or g("dob")):
            continue
        if not cn:
            issues.append((ri + 1, "缺中文姓名"))
            continue
        if not cls:
            issues.append((ri + 1, "缺班级"))
            continue
        if not dob:
            issues.append((ri + 1, "出生日期无法识别：%r" % g("dob")[:24]))
            continue
        en = re.sub(r"\s+", " ", g("en").upper()).strip()
        students.append({"id": g("id"), "cls": cls, "cn": cn, "en": en,
                         "g": norm_gender(g("g")), "dob": dob})

    # 学号为空时按行序补齐，保证服务端可导入
    for i, st in enumerate(students, 1):
        if not st["id"]:
            st["id"] = "S%03d" % i

    keys, dup = {}, []
    for i, st in enumerate(students, 1):
        for label, key in (("学号", ("id", st["id"])),
                           ("班级+姓名", ("cls", st["cls"], "cn", st["cn"]))):
            if key in keys:
                dup.append("第 %d 行与第 %d 行%s重复" % (i, keys[key], label))
            else:
                keys[key] = i
    return students, issues, dup


# ------------------------- 脱敏预览与接口 -------------------------
def mask_cn(s):
    return s[0] + "*" * (len(s) - 1) if len(s) > 1 else (s or "-")


def mask_en(s):
    return " ".join(w[0] + "***" for w in s.split()) if s else "(空)"


def mask_dob(s):
    return s[:7] + "-**" if len(s) >= 7 else s


def api(base, path_, obj=None, timeout=15):
    url = base.rstrip("/") + path_
    if obj is None:
        req = request.Request(url)
    else:
        req = request.Request(url, data=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                              headers={"Content-Type": "application/json; charset=utf-8"})
    with request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description="从 Excel/CSV 识别学生名单并导入报考系统")
    ap.add_argument("-f", "--file", required=True, help="Excel(.xlsx) 或 CSV 文件路径")
    ap.add_argument("--sheet", help="工作表名，默认第一个")
    ap.add_argument("--map", action="append", default=[], metavar="字段=表头名",
                    help="手动指定列映射，可重复，如 --map dob=出生年月")
    ap.add_argument("--url", default="http://127.0.0.1:8080", help="服务地址")
    ap.add_argument("--pass", dest="passwd", default=os.environ.get("EXAM_ADMIN_PASS", ""),
                    help="教务口令；建议用环境变量 EXAM_ADMIN_PASS 传入")
    ap.add_argument("--commit", action="store_true", help="真正写入（默认只预览）")
    ap.add_argument("--yes", action="store_true", help="跳过交互确认")
    ap.add_argument("--preview", type=int, default=3, help="脱敏预览行数，默认 3")
    args = ap.parse_args()

    path = args.file
    if not os.path.exists(path):
        sys.exit("文件不存在：" + path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xls":
        sys.exit("不支持旧版 .xls，请在 Excel 中另存为 .xlsx 或 .csv")
    if ext == ".xlsx":
        rows, sheets = read_xlsx(path, args.sheet)
        print("工作表：%s（使用：%s）" % ("、".join(sheets), args.sheet or sheets[0]))
    elif ext in (".csv", ".tsv", ".txt"):
        rows, sheets = read_csv_rows(path), ["(CSV)"]
    else:
        sys.exit("仅支持 .xlsx / .csv，当前后缀：" + ext)

    if not rows:
        sys.exit("表格为空")

    hi, mapping = detect_header(rows)
    # 手动覆盖：按表头名（规范化后）定位列
    hdr = [norm_header(x) for x in rows[hi]] + [""] * 0
    for item in args.map:
        if "=" not in item:
            sys.exit("--map 格式应为 字段=表头名，收到：" + item)
        field, col = item.split("=", 1)
        field = field.strip()
        if field not in ALIASES:
            sys.exit("未知字段 %r，可用：%s" % (field, "、".join(ALIASES)))
        key = norm_header(col)
        found = [i for i, h in enumerate(hdr) if h == key] or [i for i, h in enumerate(hdr) if key and key in h]
        if not found:
            sys.exit("找不到表头列：" + col)
        mapping[field] = found[0]

    print("表头行：第 %d 行" % (hi + 1))
    print("字段映射：" + "，".join("%s → 第%d列(%s)" % (FIELD_CN[f], c + 1, str(rows[hi][c] if c < len(rows[hi]) else ""))
                                for f, c in sorted(mapping.items())))
    missing = [FIELD_CN[f] for f in REQUIRED if f not in mapping]
    if missing:
        sys.exit("缺少必需列：" + "、".join(missing) + "\n请用 --map 字段=表头名 手动指定，例如 --map dob=出生年月")
    if "en" not in mapping:
        print("⚠ 未识别到「姓名大写」列：该字段用于考试局报名及成绩证书，导入后将为空。"
              "请尽快补全或用 --map en=列名 指定。")
    if "id" not in mapping:
        print("· 未识别到学号列，将按行序自动生成 S001、S002 …")

    students, issues, dup = build_students(rows, hi, mapping)
    classes = sorted({s["cls"] for s in students})
    print("\n识别结果：%d 名学生，%d 个班级：%s" % (len(students), len(classes), "、".join(classes)))
    print("姓名大写为空：%d 人；性别为空：%d 人" %
          (sum(1 for s in students if not s["en"]), sum(1 for s in students if not s["g"])))
    if issues:
        print("⚠ 跳过/异常行 %d 条（不打印学生姓名）：" % len(issues))
        for ln, why in issues[:15]:
            print("   第 %d 行：%s" % (ln, why))
        if len(issues) > 15:
            print("   … 另有 %d 条" % (len(issues) - 15))
    if dup:
        print("⚠ 重复项 %d 条（同班同名会导致身份匹配失败，必须处理）：" % len(dup))
        for d in dup[:10]:
            print("   " + d)

    print("\n脱敏预览（前 %d 条）：" % min(args.preview, len(students)))
    print("  %-8s %-8s %-8s %-14s %-6s %-10s" % ("学号", "班级", "中文名", "姓名大写", "性别", "出生日期"))
    for s in students[:args.preview]:
        print("  %-8s %-8s %-8s %-14s %-6s %-10s" %
              (s["id"], s["cls"], mask_cn(s["cn"]), mask_en(s["en"]), s["g"] or "-", mask_dob(s["dob"])))

    if not args.commit:
        print("\n[预览模式] 未写入任何数据。确认无误后加 --commit 导入。")
        return
    if not students:
        sys.exit("没有可导入的学生")
    if dup:
        sys.exit("存在重复项，已中止导入。请先在 Excel 中处理。")
    if not args.passwd:
        sys.exit("需要教务口令：设置环境变量 EXAM_ADMIN_PASS 或加 --pass（建议用环境变量）")

    try:
        health = api(args.url, "/api/health")
    except (URLError, HTTPError, OSError) as e:
        sys.exit("无法连接服务 %s：%s\n请先在 src/ 下执行 node server.js" % (args.url, e))
    try:
        login = api(args.url, "/api/admin/login", {"pass": args.passwd})
    except (URLError, HTTPError, OSError) as e:
        sys.exit("登录请求失败：" + str(e))
    if not login.get("ok"):
        sys.exit("教务口令不正确")
    token = login["token"]
    state = api(args.url, "/api/admin/season", {"token": token, "action": "list"})
    season = state.get("current", health.get("season", "?"))
    print("\n即将导入到当前考试季：%s（服务地址 %s）" % (season, args.url))
    print("将替换该季名单；已有提交记录的考试季会被服务端拒绝。")
    if not args.yes:
        if input("确认导入？输入 yes 继续：").strip().lower() != "yes":
            print("已取消")
            return
    result = api(args.url, "/api/admin/season",
                 {"token": token, "action": "roster", "students": students})
    if not result.get("ok"):
        sys.exit("导入失败：" + str(result.get("error", result)))
    print("✓ 已导入 %d 名学生；班级下拉已同步为：%s" %
          (result.get("count", len(students)), "、".join(result.get("classes", []))))
    print("数据已写入服务端加密文件，前端与静态目录中不含名单。")


if __name__ == "__main__":
    main()
