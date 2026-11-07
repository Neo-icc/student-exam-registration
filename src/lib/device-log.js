/* 输入时间线 + 终端设备识别（仅用 Node 内置模块）
   服务端解析 User-Agent 得到设备信息；客户端上报的信息单独存放并标注「可伪造」。
   时间一律使用服务端时钟，不信任客户端传来的时间。 */
var LOG_MAX = 5000;

function parseUA(raw){
  var ua = String(raw || "").slice(0, 500);
  var r = {type:"未知", brand:"", model:"", os:"", browser:"", app:"", ua:ua, note:""};
  if(!ua) return r;

  var tablet = /iPad|Tablet|Pad\b/i.test(ua) || (/Android/i.test(ua) && !/Mobile/i.test(ua));

  /* 内嵌 App：钉钉工作台 / 微信 / 企业微信 / QQ浏览器。
     钉钉 UA 常见形式：AliApp(DingTalk/7.6.5) com.laiwang.DingTalk，或仅 DingTalk/x.y.z。
     从钉钉工作台 H5 应用进入时，这一项是区分访问渠道的关键留痕。 */
  var dt = ua.match(/AliApp\(DingTalk\/([\d.]+)\)/i) || ua.match(/DingTalk\/([\d.]+)/i);
  var wx = ua.match(/MicroMessenger\/([\d.]+)/i);
  if(dt) r.app = "钉钉 " + dt[1];
  else if(/DingTalk|com\.laiwang\.DingTalk/i.test(ua)) r.app = "钉钉";
  else if(wx) r.app = "微信 " + wx[1];
  else if(/wxwork/i.test(ua)) r.app = "企业微信";
  else { var qq = ua.match(/MQQBrowser\/([\d.]+)/i); if(qq) r.app = "QQ浏览器 " + qq[1]; }

  /* 浏览器 */
  var b;
  if((b = ua.match(/EdgA?\/([\d.]+)/i))) r.browser = "Edge " + b[1];
  else if((b = ua.match(/OPR\/([\d.]+)/i))) r.browser = "Opera " + b[1];
  else if((b = ua.match(/Chrome\/([\d.]+)/i))) r.browser = "Chrome " + b[1];
  else if((b = ua.match(/Firefox\/([\d.]+)/i))) r.browser = "Firefox " + b[1];
  else if((b = ua.match(/Version\/([\d.]+).*Safari/i))) r.browser = "Safari " + b[1];
  if(r.app) r.browser = (r.browser ? r.browser + " / " : "") + r.app;

  /* iOS / iPadOS */
  if(/iPhone|iPad|iPod/i.test(ua)){
    var ios = ua.match(/OS (\d+[._]\d+(?:[._]\d+)?)/i);
    r.brand = "Apple";
    r.os = "iOS " + (ios ? ios[1].replace(/_/g, ".") : "?");
    r.model = /iPad/i.test(ua) ? "iPad" : (/iPod/i.test(ua) ? "iPod touch" : "iPhone");
    r.type = (/iPad/i.test(ua) || tablet) ? "平板" : "手机";
    r.note = "Apple 的 UA 不含具体机型，只能识别到设备系列 + iOS 版本";
    return r;
  }

  /* Android：尽量取 Build 前的机型串 */
  if(/Android/i.test(ua)){
    var av = ua.match(/Android\s([\d.]+)/i);
    r.os = "Android " + (av ? av[1] : "?");
    r.type = tablet ? "平板" : "手机";
    var model = "";
    var m1 = ua.match(/Android\s[^;)]*;\s*([^;)]+?)\s+Build\//i);
    if(m1) model = m1[1].trim();
    if(!model){
      var m2 = ua.match(/;\s*(HUAWEI|HONOR|Xiaomi|Redmi|MI\s?\d|POCO|OPPO|OnePlus|realme|vivo|iQOO|Meizu|Smartisan|Pixel|Nexus|samsung)[^;)]*/i);
      if(m2) model = m2[1].trim();
    }
    if(!model){
      var m3 = ua.match(/\b(SM-[A-Z0-9]+|CPH\d+|V\d{4}[A-Z]*|Pixel\s?\d+\w*|MI\s?\d+\w*|Redmi[\w\s-]*)\b/i);
      if(m3) model = m3[1].trim();
    }
    var build = ua.match(/Build\/([^;)]+)/i);
    if(build && model) model = model.replace(/Build\/.*$/, "").trim();
    r.model = model.slice(0, 60);
    if(/HUAWEI|HONOR/i.test(model)) r.brand = /HONOR/i.test(model) ? "荣耀" : "华为";
    else if(/Xiaomi|Redmi|MI\s?\d|POCO/i.test(model)) r.brand = "小米";
    else if(/OPPO|CPH/i.test(model)) r.brand = "OPPO";
    else if(/OnePlus/i.test(model)) r.brand = "一加";
    else if(/realme/i.test(model)) r.brand = "realme";
    else if(/vivo|iQOO|V\d{4}/i.test(model)) r.brand = "vivo";
    else if(/Meizu/i.test(model)) r.brand = "魅族";
    else if(/Pixel|Nexus/i.test(model)) r.brand = "Google";
    else if(/SM-|samsung/i.test(model)) r.brand = "三星";
    if(!r.model) r.note = "UA 未携带机型串，仅能识别为 Android 设备";
    return r;
  }

  /* 桌面 */
  r.type = "电脑";
  if(/Windows NT 10\.0/i.test(ua)) r.os = "Windows 10/11";
  else if(/Windows NT 6\.3/i.test(ua)) r.os = "Windows 8.1";
  else if(/Windows NT 6\.1/i.test(ua)) r.os = "Windows 7";
  else if(/Windows/i.test(ua)) r.os = "Windows";
  else if(/Mac OS X/i.test(ua)){ var mv = ua.match(/Mac OS X (\d+[._]\d+(?:[._]\d+)?)/i); r.os = "macOS " + (mv ? mv[1].replace(/_/g, ".") : ""); r.brand = "Apple"; }
  else if(/CrOS/i.test(ua)) r.os = "ChromeOS";
  else if(/Linux/i.test(ua)) r.os = "Linux";
  r.note = "桌面设备 UA 一般不含具体机型，仅能识别操作系统与浏览器";
  return r;
}

/* 客户端上报的信息：单独存放，明确标注可伪造 */
function sanitizeHint(h){
  if(!h || typeof h !== "object") return null;
  /* UA-CH 高熵值同属客户端上报，可伪造；单独列字段、CSV 中明确标注 */
  var out = {}, keys = ["ua","platform","screen","dpr","model","mobile","vendor",
    "uaModel","uaPlatform","uaPlatformVersion","uaArch","uaBitness","uaFullVersion"];
  keys.forEach(function(k){ if(h[k] !== undefined) out[k] = String(h[k]).slice(0, 150); });
  return Object.keys(out).length ? out : null;
}

function deviceLabel(d){
  if(!d) return "未知设备";
  /* 带上内嵌 App（如微信），便于区分同一机型在浏览器/微信内打开的不同终端场景 */
  return [d.type, d.brand, d.model, d.os, d.app].filter(Boolean).join(" · ") || "未知设备";
}

/* 写入一条输入事件。ctx = {ip, device, clientHint} */
function logEvent(s, sid, action, ctx, detail){
  s.logs = s.logs || [];
  s.logs.push({
    at: new Date().toISOString(),      // 服务端权威时间
    sid: sid || "",
    action: action,
    ip: (ctx && ctx.ip) || "",
    fwd: (ctx && ctx.fwd) || "",   // 参考来源 IP，可伪造，不参与任何安全判定
    device: (ctx && ctx.device) || null,
    clientHint: (ctx && ctx.clientHint) || null,
    detail: String(detail || "").slice(0, 120)
  });
  if(s.logs.length > LOG_MAX) s.logs.splice(0, s.logs.length - LOG_MAX);
  return s.logs[s.logs.length - 1];
}

module.exports = {parseUA:parseUA, sanitizeHint:sanitizeHint, deviceLabel:deviceLabel,
  logEvent:logEvent, LOG_MAX:LOG_MAX};
