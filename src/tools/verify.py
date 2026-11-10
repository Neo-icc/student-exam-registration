# -*- coding: utf-8 -*-
"""ICC全球大考报名系统 · 全量回归验证（零第三方依赖，仅用 Python 标准库）

用法：
    PORT=8093 node server.js                       # 另开终端，干净 data/ 目录
    python tools/verify.py                          # 默认 http://127.0.0.1:8093
    VERIFY_URL=http://127.0.0.1:8094 python tools/verify.py

覆盖：加密落盘、零名单启动、身份验证与信息泄露、双因子、个人信息告知、
      服务端权威时间/设备时间线、后台鉴权、加密备份恢复、攻击面回归、前端静态检查。
脚本只使用公开默认口令与随机生成的测试口令，不含任何真实凭据或学生真实数据。
本机存在全局代理时无需额外设置 NO_PROXY：回环目标自动强制直连，远端目标沿用环境代理。
"""
import json
import os
import random
import re
import string
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urlparse

BASE = os.environ.get("VERIFY_URL", "http://127.0.0.1:8093").rstrip("/")
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PASS = os.environ.get("VERIFY_ADMIN_PASS", "exam2026")


def _loopback(url):
    """目标主机是否为本地回环地址。"""
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.startswith("127.")


# 本机有全局代理（如 http_proxy=http://127.0.0.1:7286）时，urllib 默认连
# 127.0.0.1 也会走代理；停服后代理回 502，会让「服务已停」类断言假失败。
# 因此回环目标强制直连；验收远端线上实例时仍沿用环境代理，不破坏受限网络。
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_DEFAULT = urllib.request.build_opener()
OPENER = _DIRECT if _loopback(BASE) else _DEFAULT

PASS, FAIL = [], []
TOKEN = ""
CTX = {}


def check(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print("  PASS  " + name)
    else:
        FAIL.append(name + (("  <- " + str(extra)[:220]) if extra else ""))
        print("  FAIL  " + name + (("  <- " + str(extra)[:220]) if extra else ""))


def req(path, obj=None, headers=None, method=None, raw=False):
    url = BASE + path
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        h.update(headers)
    data = None
    if obj is not None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(url, data=data, headers=h, method=method or ("POST" if obj is not None else "GET"))
    try:
        with OPENER.open(r, timeout=20) as resp:
            body = resp.read()
            return resp.status, dict(resp.headers), body if raw else _parse(body)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, dict(e.headers), body if raw else _parse(body)


def proxy_channel_check():
    """确认请求通道不被本机全局代理干扰，返回 (是否通过, 说明)。"""
    direct = _loopback(BASE)
    if (OPENER is _DIRECT) != direct:
        return False, "opener 选择与目标主机不匹配：" + BASE
    if not direct:
        return True, "远端目标沿用环境代理"
    # 端口 1 恒无服务：直连应抛 URLError；若被代理接管会返回 HTTPError(502/503)。
    probe = urllib.request.Request("http://127.0.0.1:1/api/health")
    try:
        with OPENER.open(probe, timeout=3) as resp:
            return False, "回环端口 1 意外返回 HTTP %s" % resp.status
    except urllib.error.HTTPError as e:
        return False, "回环请求被环境代理接管：HTTP %s" % e.code
    except urllib.error.URLError:
        return True, ""
    except Exception as e:
        return True, "直连异常（非代理）：" + type(e).__name__


def _parse(body):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return body.decode("utf-8", "replace")


def get(path, headers=None):
    return req(path, None, headers)


def post(path, obj, headers=None):
    return req(path, obj, headers)


def admin():
    return {"X-Admin-Token": TOKEN}


def api_post(path, obj):
    return post(path, obj, admin())[2]


def rand_pass(n=16):
    return "Vf" + "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))


def future(days=30):
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


def past(days=2):
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


UA_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
UA_HUAWEI = ("Mozilla/5.0 (Linux; Android 12; HUAWEI P40 Pro Build/HUAWEIP40Pro; wv) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/108.0.0.0 "
             "Mobile Safari/537.36 MicroMessenger/8.0.40")
UA_DINGTALK = ("Mozilla/5.0 (Linux; Android 13; HUAWEI P40 Pro Build/HUAWEIP40Pro; wv) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/112.0.0.0 "
               "Mobile Safari/537.36 AliApp(DingTalk/7.6.5) com.laiwang.DingTalk")

HINT = {"ua": UA_HUAWEI, "platform": "Linux armv8l", "screen": "1200x2640", "dpr": "3",
        "model": "HUAWEI P40 Pro", "mobile": "true", "vendor": "HUAWEI",
        "uaModel": "HUAWEI P40 Pro", "uaPlatform": "Android", "uaPlatformVersion": "12.0.0",
        "uaArch": "arm", "uaBitness": "64", "uaFullVersion": "108.0.5359.128"}


def verify(cls, name, dob, **kw):
    ua = kw.pop("ua", None)
    b = {"cls": cls, "name": name, "dob": dob, "nameOk": False,
         "privacyOk": True, "deviceHint": HINT}
    b.update(kw)
    return post("/api/verify", b, {"User-Agent": ua or UA_HUAWEI})[2]


def section(t):
    print("\n---- " + t + " ----")


def main():
    global TOKEN
    print("目标服务：" + BASE)
    st, _, health = get("/api/health")
    if not (st == 200 and isinstance(health, dict) and health.get("ok")):
        print("服务不可用，先启动： PORT=8093 node server.js")
        sys.exit(2)

    # ===== A 启动配置 / 零名单 =====
    section("A 启动配置与零名单")
    check("A1 健康检查返回当前考试季", health.get("season") == "2026-summer", health)
    _, hb, boot = get("/api/boot")
    check("A2 /api/boot 不下发任何学生名单",
          "students" not in boot and "张思远" not in json.dumps(boot, ensure_ascii=False), list(boot.keys()))
    check("A3 个人信息处理告知文本已下发",
          "个人信息" in str(boot.get("privacyNote", "")), str(boot.get("privacyNote", ""))[:80])
    check("A4 下发双因子开关与合规开关及服务端时间",
          "secondFactor" in boot and "privacyRequired" in boot and "serverTime" in boot, boot.get("secondFactor"))
    check("A5 /api/boot 不含任何真实出生日期",
          "2009-03-12" not in json.dumps(boot, ensure_ascii=False))
    hs = {k.lower(): v for k, v in hb.items()}
    check("A6 安全响应头齐全",
          "no-store" in hs.get("cache-control", "") and hs.get("x-frame-options") == "DENY"
          and "nosniff" in hs.get("x-content-type-options", "") and "content-security-policy" in hs,
          {k: hs.get(k) for k in ["cache-control", "x-frame-options", "x-content-type-options"]})

    # ===== B 加密落盘 / 静态防护 =====
    section("B 加密落盘与静态资源防护")
    d = os.path.join(SRC, "data")
    season_file = os.path.join(d, "seasons", "2026-summer.json")
    raw = open(season_file, "r", encoding="utf-8").read() if os.path.exists(season_file) else ""
    check("B1 考试季文件为 AES-256-GCM 密文且无明文姓名",
          raw.startswith("EXAMENC1:") and "张思远" not in raw, raw[:40])
    key_file = os.path.join(d, ".key")
    check("B2 数据密钥独立存放于 data/.key", os.path.exists(key_file))
    check("B3 静态目录遍历读取密钥被拒",
          req("/../data/.key", raw=True)[0] == 403 or req("/%2e%2e/data/.key", raw=True)[0] == 403)
    s_, _, kbody = req("/data/.key", raw=True)
    real_key = open(key_file, "rb").read() if os.path.exists(key_file) else b""
    check("B4 /data/.key 不会返回密钥内容",
          kbody != real_key and real_key not in kbody, s_)
    tmps = [f for f in os.listdir(d) if ".tmp-" in f] + \
           [f for f in os.listdir(os.path.join(d, "seasons")) if ".tmp-" in f]
    check("B5 原子写入无临时文件残留", not tmps, tmps)

    # ===== C 后台登录与窗口准备 =====
    section("C 后台登录与报考窗口")
    _, _, lg = post("/api/admin/login", {"pass": DEFAULT_PASS})
    check("C1 默认口令可登录（干净环境）", bool(lg.get("ok") and lg.get("token")), lg)
    TOKEN = lg.get("token", "")
    _, _, st0 = get("/api/admin/state", admin())
    check("C2 令牌可读取后台状态", bool(st0.get("ok")), str(st0)[:120])
    cfg = api_post("/api/admin/season", {"action": "config", "start": past(3), "end": future(30)})
    check("C3 报考窗口可配置为开放", bool(cfg.get("ok")), cfg)
    _, _, boot2 = get("/api/boot")
    check("C4 窗口状态已变为 open", boot2.get("win") == "open", boot2.get("win"))

    # ===== D 身份验证 / 信息泄露 =====
    section("D 身份验证与信息泄露防护")
    r = verify("IG1", "张思远", "2009-03-12", privacyOk=False)
    check("D1 未同意告知直接返回 privacy，且不做姓名匹配", r.get("code") == "privacy", r)
    r = verify("IG1", "不存在的人", "2009-03-12")
    check("D2 姓名/班级不匹配返回 nomatch 且无任何敏感字段",
          r.get("code") == "nomatch" and not any(k in r for k in ["student", "record", "dob", "masked"]), r)
    real_dob = "2009-03-12"
    r = verify("IG1", "张思远", "2000-01-01")
    dumped = json.dumps(r, ensure_ascii=False)
    check("D3 出生日期错误返回 nameCheck 并带失败计数/锁定字段",
          r.get("code") == "nameCheck" and "fails" in r and "locked" in r, r)
    check("D4 失败响应不泄露学籍真实 dob / 完整档案 / 已提交记录",
          real_dob not in dumped and "student" not in r and "record" not in r
          and "ZHANG SIYUAN" not in dumped and "2009-03-12" not in dumped,
          dumped[:180])
    check("D5 失败响应只保留学生自填日期作为 tryDob", r.get("tryDob") == "2000-01-01", r.get("tryDob"))
    r = verify("IG1", "ZHANG SIYUAN", real_dob)
    check("D6 支持大写拼音姓名通过验证", r.get("code") == "ok", r.get("code"))
    check("D7 验证通过仅返回本人档案", r.get("student", {}).get("id") == "S001"
          and r.get("student", {}).get("dob") == real_dob, str(r.get("student"))[:120])
    _, _, state1 = get("/api/admin/state", admin())
    acts = [x.get("action") for x in state1.get("logs", [])]
    check("D8 同意/拒绝告知与验证通过均留痕",
          all(a in acts for a in ["privacy_denied", "privacy_consent", "verify_ok", "verify_fail"]), acts[-12:])
    last = [x for x in state1.get("logs", []) if x.get("action") == "verify_ok"][-1]
    check("D9 时间线使用服务端权威时间并含设备", bool(last.get("at")) and bool(last.get("device")), last.get("at"))
    r_dt = verify("IG1", "张思远", real_dob, ua=UA_DINGTALK)
    _, _, state_dt = get("/api/admin/state", admin())
    last_dt = [x for x in state_dt.get("logs", []) if x.get("action") == "verify_ok"][-1]
    app_dt = ((last_dt.get("device") or {}).get("app") or "")
    check("D10 钉钉工作台内置浏览器可验证且时间线识别钉钉渠道",
          r_dt.get("code") == "ok" and "钉钉" in app_dt,
          {"code": r_dt.get("code"), "app": app_dt})

    # ===== E 双因子 =====
    section("E 第二验证因子（出生日期 + 学号后四位）")
    cfg = api_post("/api/admin/season", {"action": "config", "secondFactor": "sid4"})
    check("E1 可开启双因子", cfg.get("secondFactor") == "sid4", cfg)
    _, _, boot3 = get("/api/boot")
    check("E2 /api/boot 下发双因子配置", boot3.get("secondFactor") == "sid4", boot3.get("secondFactor"))
    r = verify("IG1", "张思远", real_dob)
    check("E3 双因子开启后仅凭出生日期不再通过",
          r.get("code") != "ok" and "student" not in r, r.get("code"))
    r = verify("IG1", "张思远", real_dob, sid4="9999")
    check("E4 学号后四位错误不通过且提示需核对双因子",
          r.get("code") != "ok" and r.get("secondFactor") is True, r.get("code"))
    # S001 的数字部分只有 3 位，必须左补零为 "0001"（历史 bug 回归）
    r = verify("IG1", "张思远", real_dob, sid4="0001")
    check("E5 生日 + 学号后四位正确才通过（S001→0001 左补零）", r.get("code") == "ok", r.get("code"))
    cfg = api_post("/api/admin/season", {"action": "config", "secondFactor": "off"})
    check("E6 可关闭双因子", cfg.get("secondFactor") == "off", cfg)

    # ===== F 提交：服务端权威时间 / 设备 / 去重 =====
    section("F 提交记录、服务端权威时间与设备时间线")
    forged = {"ok": True, "errText": "", "sig1": "张三", "sig2": "", "picked": {"math": ["P1-WMA11"]},
              "other": {"s": "", "u": ""}, "agree": True,
              "subAt": "1999-01-01T00:00:00.000Z", "modCount": 99,
              "unlocked": True, "paper": "已签", "cn": "冒名者", "dob": "1999-01-01"}
    _, _, pr = post("/api/push", {"sid": "S001", "dob": real_dob, "record": forged,
                                  "deviceHint": HINT},
                    {"User-Agent": UA_HUAWEI, "X-Forwarded-For": "203.0.113.77"})
    check("F1 提交一条记录成功", bool(pr.get("ok")), str(pr)[:180])
    rec = pr.get("record", {})
    CTX["subAt"] = rec.get("subAt")
    check("F2 身份字段由服务端重建，客户端伪造无效",
          rec.get("cn") == "张思远" and rec.get("dob") == real_dob, str(rec)[:160])
    check("F3 提交时间为服务端时间，不接受客户端 1999 年",
          str(rec.get("subAt", "")).startswith(str(datetime.now().year)), rec.get("subAt"))
    check("F4 权限字段由服务端重置（unlocked/paper/modCount）",
          rec.get("unlocked") is False and rec.get("paper") == "未签" and rec.get("modCount") == 0,
          {k: rec.get(k) for k in ["unlocked", "paper", "modCount"]})
    check("F5 服务端记录终端设备型号（华为 P40 Pro / 微信）",
          "P40 Pro" in str(rec.get("lastDevice", "")) and "微信" in str(rec.get("lastDevice", "")),
          rec.get("lastDevice"))
    _, _, pr2 = post("/api/push", {"sid": "S001", "dob": real_dob, "record": forged},
                     {"User-Agent": UA_HUAWEI})
    check("F6 相同内容心跳同步不刷新提交时间、不增加修改次数",
          pr2.get("record", {}).get("subAt") == CTX["subAt"] and pr2.get("record", {}).get("modCount") == 0,
          pr2.get("record", {}).get("subAt"))
    _, _, state2 = get("/api/admin/state", admin())
    sub = [x for x in state2.get("logs", []) if x.get("action") == "submit"][-1]
    check("F7 提交事件写入时间线且含 UA-CH 客户端字段",
          bool(sub.get("at")) and (sub.get("clientHint") or {}).get("uaModel") == "HUAWEI P40 Pro",
          str(sub.get("clientHint"))[:160])
    check("F8 参考来源 IP 单独记录为 fwd（可伪造，不参与判定）",
          sub.get("fwd") == "203.0.113.77" and "127.0.0.1" in str(sub.get("ip")),
          {"ip": sub.get("ip"), "fwd": sub.get("fwd")})
    # 关闭窗口后越权写入
    api_post("/api/admin/season", {"action": "config", "end": past(1)})
    _, _, pc = post("/api/push", {"sid": "S001", "dob": real_dob, "record": forged},
                    {"User-Agent": UA_HUAWEI})
    check("F9 窗口关闭后拒绝写入（伪造 unlocked 也无效）", pc.get("ok") is False, str(pc)[:140])
    api_post("/api/admin/season", {"action": "config", "end": future(30)})

    # ===== G 后台鉴权与改口令 =====
    section("G 后台鉴权与会话管理")
    _, _, no = get("/api/admin/state")
    check("G1 未带令牌读取后台状态被拒", no.get("ok") is False, str(no)[:100])
    _, _, bad = post("/api/admin/login", {"pass": "definitely-wrong"})
    check("G2 错误口令登录被拒", bad.get("ok") is False, str(bad)[:100])
    _, _, lg2 = post("/api/admin/login", {"pass": DEFAULT_PASS})
    t2 = lg2.get("token", "")
    newpass = rand_pass()
    _, _, cp = post("/api/admin/passwd", {"newPass": newpass}, {"X-Admin-Token": TOKEN})
    check("G3 可通过接口修改教务口令", cp.get("ok") is True, str(cp)[:100])
    _, _, oldtok = get("/api/admin/state", {"X-Admin-Token": t2})
    check("G4 改口令后其他会话令牌立即失效", oldtok.get("ok") is False, str(oldtok)[:100])
    _, _, newtok = get("/api/admin/state", {"X-Admin-Token": TOKEN})
    check("G5 发起改口令的当前会话仍可用", newtok.get("ok") is True)
    _, _, weak = post("/api/admin/passwd", {"newPass": "123"}, {"X-Admin-Token": TOKEN})
    check("G6 弱口令被拒", weak.get("ok") is False, str(weak)[:100])
    CTX["newpass"] = newpass

    # ===== H 加密备份 / 恢复 =====
    section("H 加密备份与恢复")
    BPASS = rand_pass(14)
    CTX["bpass"] = BPASS
    bk = api_post("/api/admin/backup", {"backupPass": BPASS})
    check("H1 导出加密备份成功", bool(bk.get("ok")) and bk.get("format") == "EXAMBAK1", str(bk)[:120])
    text = bk.get("text", "")
    CTX["text"] = text
    CTX["checksum"] = bk.get("checksum")
    check("H2 备份文本为密文，不含明文姓名/口令",
          text.startswith("EXAMBAK1:") and "张思远" not in text and BPASS not in text
          and DEFAULT_PASS not in text)
    weakbk = api_post("/api/admin/backup", {"backupPass": "abc"})
    check("H3 弱备份口令被拒", weakbk.get("ok") is False, str(weakbk)[:120])
    wrong = api_post("/api/admin/restore", {"text": text, "backupPass": "WrongPass123",
                                                  "overwrite": True, "setCurrent": True})
    check("H4 错误备份口令恢复被拒", wrong.get("ok") is False, str(wrong)[:120])
    # 篡改密文中段：末尾 base64 量子可能含无效位/填充，改尾部字符偶尔解码后原文不变，
    # 会让这条断言随机误判；改中段字节必定触发 GCM 认证失败。
    mid = len(text) // 2
    tampered = text[:mid] + ("A" if text[mid] != "A" else "B") + text[mid + 1:]
    tam = api_post("/api/admin/restore", {"text": tampered, "backupPass": BPASS,
                                                "overwrite": True, "setCurrent": True})
    check("H5 备份被篡改恢复被拒", tam.get("ok") is False, str(tam)[:120])
    ck = api_post("/api/admin/restore", {"text": text, "backupPass": BPASS,
                                               "checksum": "deadbeef", "overwrite": True, "setCurrent": True})
    check("H6 校验和不匹配恢复被拒", ck.get("ok") is False, str(ck)[:120])
    before = get("/api/admin/state", admin())[2]
    CTX["students_before"] = len(before.get("students", []))
    CTX["records_before"] = len(before.get("records", {}))
    rs = api_post("/api/admin/restore", {"text": text, "backupPass": BPASS,
                                               "checksum": bk.get("checksum"),
                                               "overwrite": True, "setCurrent": True})
    check("H7 正确口令恢复成功且记录数还原",
          bool(rs.get("ok")) and rs.get("records") == CTX["records_before"] == 1, str(rs)[:180])
    _, _, after = get("/api/admin/state", admin())
    check("H8 名单与提交记录完整还原",
          len(after.get("students", [])) == CTX["students_before"] == 14
          and "S001" in after.get("records", {})
          and after["records"]["S001"].get("subAt") == CTX["subAt"],
          {"students": len(after.get("students", [])), "records": len(after.get("records", {}))})
    bad_struct = api_post("/api/admin/restore", {"text": "EXAMBAK1:" + "AAAA",
                                                       "backupPass": BPASS, "overwrite": True})
    check("H9 非备份格式被拒", bad_struct.get("ok") is False, str(bad_struct)[:120])

    # ===== I 攻击面回归 =====
    section("I 攻击面回归")
    _, _, leak = get("/api/boot")
    check("I1 公开启动接口不含任何学生 PII",
          "张思远" not in json.dumps(leak, ensure_ascii=False) and "2009-03-12" not in json.dumps(leak, ensure_ascii=False))
    _, _, pd = post("/api/push", {"sid": "S001", "dob": "1999-01-01", "record": forged})
    check("I2 伪造 dob 写他人记录被拒", pd.get("ok") is False, str(pd)[:120])
    s_bad, _, badbody = req("/../../server.js", raw=True)
    badbytes = badbody if isinstance(badbody, bytes) else b""
    check("I3 静态路径穿越访问服务端源码被拒",
          s_bad == 403 or b"var http" not in badbytes, s_bad)
    _, _, badtok = get("/api/admin/state", {"X-Admin-Token": "forged-token"})
    check("I4 伪造令牌被拒", badtok.get("ok") is False)
    # 工单分支：nameOk=true 建工单，工单文本不得含学籍真实 dob，且前端不放行
    r = verify("IG2", "王一诺", "2000-02-02", nameOk=True)
    check("I5 姓名确认后建纠错工单且不泄露真实 dob",
          r.get("code") == "ticket" and real_dob not in json.dumps(r, ensure_ascii=False)
          and "2009-01-22" not in json.dumps(r, ensure_ascii=False), str(r)[:160])
    html = open(os.path.join(SRC, "public", "index.html"), "r", encoding="utf-8").read()
    seg = html.split('if(res.code === "ticket")')[1].split("SYNC_LOCK = true")[0]
    check("I6 前端 ticket 分支不放行验证",
          "S.vrf = false" in seg and "S.vrf = true" not in seg,
          "ticket 分支仍设置 vrf")
    check("I7 在线模式前端零名单（STUDENTS=[]）", "var STUDENTS = []" in html)
    check("I8 前端采集 UA-CH 高熵值并标注可伪造",
          "getHighEntropyValues" in html and "uaModel" in html and "可伪造" in html)
    # 生产前端不得预置虚构名单，也不得保留可在服务不可达时对虚构数据验证的离线分支
    check("I13 生产前端不预置虚构名单（无 DEMO_ROSTER）",
          "DEMO_ROSTER" not in html and "张思远" not in html and "李佳怡" not in html,
          "前端仍内嵌虚构示例学生")
    check("I14 服务不可达时只读提示、不提供离线填写",
          "doVerifyLocal" not in html and "nameCheckHTML" not in html
          and "SERVER_DOWN" in html and "报名服务暂不可用" in html,
          "仍保留离线验证回退或缺少只读阻断")
    # 须知与页脚不得重复同一句追查提示
    check("I15 须知与第 1 步页脚无重复追查句",
          html.count("本页访问已记录，非本人查询将被追查") == 1,
          "追查句在前端重复出现")
    # 页首只显示系统名，不再把冗长的考试季名拼到标题后面
    check("I16 页首标题只显示系统名、不拼接考试季名",
          't.textContent = "ICC全球大考报名系统"' in html
          and 'ICC全球大考报名系统 · " +' not in html,
          "页首仍在拼接考试季名")
    # 失败锁定：第 3 次当次即返回 locked，且按「出口 IP + 目标学生」隔离
    r1 = verify("AS1", "刘雨桐", "2000-03-03")
    r2 = verify("AS1", "刘雨桐", "2000-03-03")
    r3 = verify("AS1", "刘雨桐", "2000-03-03")
    check("I9 第 3 次失败当次即返回锁定信息",
          bool(r3.get("locked")) and bool(r3.get("until")) and r3.get("fails") == 3,
          {k: r3.get(k) for k in ["code", "fails", "locked", "until"]})
    r4 = verify("AS1", "刘雨桐", "2000-03-03")
    check("I10 锁定期内请求直接返回 locked", r4.get("code") == "locked", r4.get("code"))
    r5 = verify("AS1", "赵子睿", "2008-09-09")
    check("I11 共享出口 IP 下另一学生仍可正常验证（锁定按目标隔离）",
          r5.get("code") == "ok", r5.get("code"))
    # 核心回归：同一学生可用中文名或大写拼音验证；若按输入姓名计数，交替写法即可绕过次数限制
    a1 = verify("AS2", "孙嘉禾", "2000-04-04")
    a2 = verify("AS2", "SUN JIAHE", "2000-04-04")
    a3 = verify("AS2", "孙嘉禾", "2000-04-04")
    check("I12 中文名/拼音交替不能绕过失败锁定（按学生 ID 累计 1→2→3）",
          a1.get("fails") == 1 and a2.get("fails") == 2
          and a3.get("fails") == 3 and bool(a3.get("locked")),
          [a1.get("fails"), a2.get("fails"), a3.get("fails"), a3.get("locked")])

    # ===== J 语法与结构 =====
    section("J 结构完整性")
    server_src = open(os.path.join(SRC, "server.js"), encoding="utf-8").read()
    check("J1 备份模块与服务端均已接入",
          "require(\"./lib/backup\")" in server_src
          and os.path.exists(os.path.join(SRC, "lib", "backup.js")))
    check("J2 钉钉工作台 iframe 兼容开关已接入服务端",
          "_examDingTalk" in server_src and "EXAM_FRAME_ANY" in server_src
          and "frame-ancestors *" in server_src)
    # 品牌更名后，教务必须能通过 config 改档案来源说明与纸质签署说明（含大考名称）
    _ = api_post("/api/admin/season", {"action": "config",
                                       "srcNote": "全球大考报名说明_test", "paperNote": "纸质签署说明_test"})
    _, _, st_cfg = get("/api/admin/state", admin())
    check("J3 教务可修改档案来源说明与纸质签署说明",
          st_cfg.get("srcNote") == "全球大考报名说明_test"
          and st_cfg.get("paperNote") == "纸质签署说明_test",
          {"srcNote": st_cfg.get("srcNote"), "paperNote": st_cfg.get("paperNote")})
    # 品牌更名必须同时覆盖「存在考试季数据里的可配置文案」：曾出现代码默认文案已改净、
    # 但线上历史考试季仍存旧系统名与 CAIE 字样，学生验证前实际看到的是旧文案。
    OLD_BRAND = ["CAIE", "考试局", "学生报考信息确认"]
    def all_strings(v):
        if isinstance(v, str): return [v]
        if isinstance(v, dict): return [s for x in v.values() for s in all_strings(x)]
        if isinstance(v, list): return [s for x in v for s in all_strings(x)]
        return []
    m_srv = re.search(r'var DEFAULT_PRIVACY_NOTE = "([^"]+)"', server_src)
    m_fe = re.search(r'var PRIVACY_NOTE = "([^"]+)"', html)
    check("J4 默认个人信息处理告知无旧品牌且前后端一致",
          bool(m_srv) and bool(m_fe) and m_srv.group(1) == m_fe.group(1)
          and not any(o in m_srv.group(1) for o in OLD_BRAND),
          {"srv": bool(m_srv), "fe": bool(m_fe), "equal": bool(m_srv and m_fe and m_srv.group(1) == m_fe.group(1))})
    _, _, boot_brand = get("/api/boot")
    bad_brand = [s[:80] for s in all_strings(boot_brand) if any(o in s for o in OLD_BRAND)]
    check("J5 公开启动接口全部文案无旧品牌字样", not bad_brand, bad_brand)
    _ = api_post("/api/admin/season", {"action": "config",
                                       "privacyNote": "ICC全球大考报名系统_test告知"})
    _, _, boot_pv = get("/api/boot")
    check("J6 教务可修改个人信息处理告知并下发学生端",
          boot_pv.get("privacyNote") == "ICC全球大考报名系统_test告知",
          boot_pv.get("privacyNote"))

    # ===== K 钉钉工作台内嵌 =====
    # 钉钉 PC 工作台用 iframe 打开 H5 首页；普通浏览器必须继续禁止嵌套防点击劫持。
    section("K 钉钉工作台内嵌兼容")
    def hdr(hs, key):
        low = key.lower()
        for k, v in hs.items():
            if k.lower() == low:
                return v
        return ""
    _, h_plain, _ = get("/", {"User-Agent": UA_IPHONE})
    check("K1 普通浏览器仍禁止被 iframe 嵌套",
          hdr(h_plain, "X-Frame-Options") == "DENY"
          and "frame-ancestors 'none'" in hdr(h_plain, "Content-Security-Policy"),
          hdr(h_plain, "X-Frame-Options"))
    _, h_dt, _ = get("/", {"User-Agent": UA_DINGTALK})
    check("K2 钉钉客户端首页允许工作台 iframe 嵌套",
          hdr(h_dt, "X-Frame-Options") != "DENY"
          and "frame-ancestors *" in hdr(h_dt, "Content-Security-Policy")
          and "frame-ancestors 'none'" not in hdr(h_dt, "Content-Security-Policy"),
          hdr(h_dt, "X-Frame-Options"))
    _, h_wx, _ = get("/", {"User-Agent": UA_HUAWEI})
    check("K3 非钉钉 UA 不能放宽嵌套策略",
          hdr(h_wx, "X-Frame-Options") == "DENY"
          and "frame-ancestors 'none'" in hdr(h_wx, "Content-Security-Policy"))
    _, h_api, _ = get("/api/boot", {"User-Agent": UA_DINGTALK})
    check("K4 钉钉端接口响应同样不带 DENY（避免控制台报错）",
          hdr(h_api, "X-Frame-Options") != "DENY")

    # ===== L 验证通道可移植性 =====
    # 本机全局代理会把 127.0.0.1 请求也转给代理，曾导致回归假失败。
    section("L 验证通道可移植性")
    ok_ch, why_ch = proxy_channel_check()
    check("L1 验证请求不受本机全局代理干扰（回环直连 / 远端沿用代理）", ok_ch, why_ch)

    print("\n===== 汇总：PASS %d / FAIL %d =====" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  - " + f)
    # 输出供「换环境恢复」测试的上下文（不含任何真实凭据）
    out = {"text": CTX.get("text", ""), "bpass": CTX.get("bpass", ""),
           "subAt": CTX.get("subAt", ""), "checksum": CTX.get("checksum", "")}
    tmp = os.environ.get("VERIFY_TMP", r"D:\Apps\WorkBuddy\.tmp")
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "verify-context.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
