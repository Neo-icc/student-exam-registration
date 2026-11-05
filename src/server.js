/* 学生报考系统 · 服务端
   零依赖，仅用 Node 内置模块。数据按「考试季」分文件存放。
   启动： node server.js    （端口可用环境变量 PORT 覆盖） */
var http = require("http"), fs = require("fs"), path = require("path"), crypto = require("crypto");

var PORT = process.env.PORT || 8080;
var ROOT = __dirname;
var DATA = path.join(ROOT, "data");
var SEASONS = path.join(DATA, "seasons");
var IDX = path.join(DATA, "index.json");
var ADMINF = path.join(DATA, "admin.json");

function mkdirp(p){ if(!fs.existsSync(p)) fs.mkdirSync(p, {recursive:true}); }
function readJSON(p, def){ try{ return JSON.parse(fs.readFileSync(p, "utf8")); }catch(e){ return def; } }
function writeJSON(p, o){ mkdirp(path.dirname(p)); fs.writeFileSync(p, JSON.stringify(o, null, 2), "utf8"); }
mkdirp(SEASONS);

/* ---------- 工具 ---------- */
function pad(n){ return n<10 ? "0"+n : ""+n; }
function fmtDT(d){ return d.getFullYear()+"年"+(d.getMonth()+1)+"月"+d.getDate()+"日 "+pad(d.getHours())+":"+pad(d.getMinutes()); }
function winText(w){ return fmtDT(new Date(w.start))+" 至 "+fmtDT(new Date(w.end)); }
function normDob(v){
  var p = String(v||"").trim().split(/\D+/).filter(function(x){ return x!==""; });
  if(p.length===3 && p[0].length===4 && p[1].length<=2 && p[2].length<=2){
    var mm=p[1], dd=p[2];
    return p[0]+"-"+(mm.length<2?"0"+mm:mm)+"-"+(dd.length<2?"0"+dd:dd);
  }
  var d = String(v||"").replace(/\D/g,"");
  if(d.length===8) return d.slice(0,4)+"-"+d.slice(4,6)+"-"+d.slice(6,8);
  return String(v||"").trim();
}
function upper(v){ return String(v||"").toUpperCase().replace(/\s+/g," ").trim(); }
function maskCn(s){ var t=String(s||"").trim(); return t.length<=1 ? t : t[0]+new Array(t.length).join("*"); }
function nowISO(){ return new Date().toISOString(); }

/* ---------- 种子数据（首次运行生成，之后以 data/seasons/*.json 为准） ---------- */
var SEED_SUBJECTS = [
  {k:"math",n:"数学",en:"Mathematics",groups:[
    {n:"",units:["P1-WMA11","P2-WMA12","P3-WMA13","P4-WMA14","S1-WST01","S2-WST02","S3-WST03","M1-WME01","M2-WME02","M3-WME03","F1-WFM01","F2-WFM02","F3-WFM03","D1-WDM11"]},
    {n:"Cashin（合卷）",units:["基数Cashin-YMA01","进数Cashin-YFM01"]}
  ]},
  {k:"biz",n:"经商",en:"Business",groups:[
    {n:"经济 Economics",units:["经济U1-WEC11","经济U2-WEC12","经济U3-WEC13","经济U4-WEC14","经济U1U2 Cashin-XEC11","经济U1U2U3U4 Cashin-YEC11"]},
    {n:"商业 Business",units:["商业U1-WBS11","商业U2-WBS12","商业U3-WBS13","商业U4-WBS14","商业U1U2 Cashin-XBS11","商业U1U2U3U4 Cashin-YBS11"]},
    {n:"会计 Accounting",units:["会计U1-WAC11","会计U2-WAC12","会计U1 Cashin-XAC11","会计U1U2 Cashin-YAC11"]}
  ]},
  {k:"sci",n:"科学",en:"Sciences",groups:[
    {n:"物理 Physics",units:["物理U1-WPH11","物理U2-WPH12","物理U3-WPH13","物理U4-WPH14","物理U5-WPH15","物理U6-WPH16","物理123 Cashin-XPH11","物理123456 Cashin-YPH11"]},
    {n:"化学 Chemistry",units:["化学U1-WCH11","化学U2-WCH12","化学U3-WCH13","化学U4-WCH14","化学U5-WCH15","化学U6-WCH16","化学123 Cashin-XCH11","化学123456 Cashin-YCH11"]},
    {n:"生物 Biology",units:["生物U1-WBI11","生物U2-WBI12","生物U3-WBI13","生物U4-WBI14","生物U5-WBI15","生物U6-WBI16","生物123 Cashin-XBI11","生物123456 Cashin-YBI11"]}
  ]},
  {k:"oth",n:"其他",en:"Other",free:true}
];
var SEED_STUDENTS = [
  {id:"S001",cls:"IG1",cn:"张思远",en:"ZHANG SIYUAN",g:"男",dob:"2009-03-12"},
  {id:"S002",cls:"IG1",cn:"李佳怡",en:"LI JIAYI",g:"女",dob:"2009-07-04"},
  {id:"S003",cls:"IG2",cn:"王一诺",en:"WANG YINUO",g:"女",dob:"2009-01-22"},
  {id:"S004",cls:"IG2",cn:"陈子涵",en:"CHEN ZIHAN",g:"男",dob:"2009-11-30"},
  {id:"S005",cls:"AS1",cn:"刘雨桐",en:"LIU YUTONG",g:"女",dob:"2008-05-18"},
  {id:"S006",cls:"AS1",cn:"赵子睿",en:"ZHAO ZIRUI",g:"男",dob:"2008-09-09"},
  {id:"S007",cls:"AS2",cn:"孙嘉禾",en:"SUN JIAHE",g:"女",dob:"2008-02-14"},
  {id:"S008",cls:"AS2",cn:"周慕辰",en:"ZHOU MUCHEN",g:"男",dob:"2008-04-26"},
  {id:"S009",cls:"AS3",cn:"吴静怡",en:"WU JINGYI",g:"女",dob:"2008-08-15"},
  {id:"S010",cls:"AS3",cn:"郑浩然",en:"ZHENG HAORAN",g:"男",dob:"2008-12-03"},
  {id:"S011",cls:"A21",cn:"何思远",en:"HE SIYUAN",g:"男",dob:"2007-06-11"},
  {id:"S012",cls:"A21",cn:"黄诗涵",en:"HUANG SHIHAN",g:"女",dob:"2007-10-20"},
  {id:"S013",cls:"A22",cn:"徐乐言",en:"XU LEYAN",g:"女",dob:"2007-03-08"},
  {id:"S014",cls:"A22",cn:"林嘉树",en:"LIN JIASHU",g:"男",dob:"2007-09-17"}
];
var SEED_NOTICES = [
  "本申请<b>每人仅可提交一次</b>。提交后本人不能自行修改或重复提交；确需变更的，须由本人向教务提出申请，经教务处理后方为有效。",
  "出生日期是本系统核验本人身份的唯一凭据，请勿告知他人。本页访问已记录，非本人查询将被追查。",
  "姓名大写拼音、性别、出生日期将用于<b>考试局报名及成绩证书</b>，须逐项核对；如有错误请勾选「信息有误」写明正确内容，由教务更正后再提交，不要将错就错。",
  "线上签名即确认本人已核阅并确认上述基本信息无误。班级纸质确认表<b>仅确认报考科目与单元</b>，班会期间须逐项核对后本人签名，纸质件留档。",
  "未在规定时间内提交视为自动放弃本次报考；窗口关闭后系统锁定，仅可查看已提交内容，不再受理提交与修改。"
];
var SEED_SRC_NOTE = "以下信息由教务根据<b>入学学籍表</b>生成，请逐项核对。<b>姓名大写拼音将用于考试局报名及成绩证书</b>，如与身份证件不一致，须立即提交更正，否则可能影响考试成绩与证书发放。";
var SEED_PAPER_NOTE = "本人已在线上核对并确认本人基本信息（姓名大写拼写、性别、出生日期）无误；本次签字仅确认下列报考科目与单元，请逐项核对后签名。";

function newSeason(id, name, start, end, classes, subjects, notices, students){
  return {id:id, name:name||id, window:{start:start, end:end}, classes:classes||[],
    subjects:subjects||SEED_SUBJECTS, notices:notices||SEED_NOTICES.slice(),
    srcNote:SEED_SRC_NOTE, paperNote:SEED_PAPER_NOTE,
    students:students||[], overrides:{}, records:{}, tickets:{}, alerts:[],
    archived:false, createdAt:nowISO()};
}

/* ---------- 数据读写 ---------- */
var FAIL_MAX = 3, FAIL_LOCK_MIN = 15;
var failMap = {};   // ip -> {n, until}
var tokens = {};    // token -> expire ms

function idx(){ return readJSON(IDX, null); }
function ensureSeed(){
  var i = idx();
  if(!i){
    var s = newSeason("2026-summer", "2026 年夏季 CAIE 考试报名", "2026-10-25T08:00", "2026-11-05T18:00",
      ["IG1","IG2","AS1","AS2","AS3","A21","A22"], SEED_SUBJECTS, SEED_NOTICES.slice(), SEED_STUDENTS.map(function(x){return Object.assign({},x);}));
    writeJSON(path.join(SEASONS, s.id+".json"), s);
    writeJSON(IDX, {current:s.id});
    writeJSON(ADMINF, {pass:"exam2026"});
    i = {current:s.id};
  }
  return i;
}
ensureSeed();
function seasonFile(id){ return path.join(SEASONS, id+".json"); }
function getSeason(id){ return readJSON(seasonFile(id), null); }
function putSeason(s){ writeJSON(seasonFile(s.id), s); }
function curId(){ return idx().current; }
function cur(){ return getSeason(curId()); }
function seasonList(){
  return fs.readdirSync(SEASONS).filter(function(f){ return /\.json$/.test(f); }).map(function(f){
    var s = readJSON(path.join(SEASONS,f), null); if(!s) return null;
    return {id:s.id, name:s.name, window:s.window, windowText:winText(s.window), archived:!!s.archived,
      students:(s.students||[]).length, records:Object.keys(s.records||{}).length};
  }).filter(Boolean);
}
/* 主数据 + 覆写层合成后的档案 */
function merged(s, id){
  var b = (s.students||[]).filter(function(x){ return x.id===id; })[0]; if(!b) return null;
  var o = (s.overrides||{})[id];
  var m = o ? Object.assign({}, b, o) : Object.assign({}, b);
  m.en = upper(m.en);
  m._chg = (o && o._chg) || null;
  m._ver = (o && o._ver) || 1;
  return m;
}
function winStateOf(s){
  var n = Date.now();
  if(n < new Date(s.window.start).getTime()) return "before";
  if(n > new Date(s.window.end).getTime()) return "closed";
  return "open";
}
function pushAlert(s, sid, ok, ip){
  s.alerts = s.alerts || [];
  s.alerts.unshift({at:nowISO(), sid:sid, ok:!!ok, ip:ip||""});
  if(s.alerts.length>200) s.alerts.length = 200;
}

/* ---------- HTTP ---------- */
var MIME = {".html":"text/html; charset=utf-8", ".js":"text/javascript; charset=utf-8", ".css":"text/css; charset=utf-8",
  ".json":"application/json; charset=utf-8", ".svg":"image/svg+xml", ".ico":"image/x-icon", ".png":"image/png", ".md":"text/markdown; charset=utf-8"};

function send(res, code, body, type){
  res.writeHead(code, {"Content-Type": type||"application/json; charset=utf-8", "Cache-Control":"no-store"});
  res.end(body);
}
function json(res, obj){ send(res, 200, JSON.stringify(obj)); }
function err(res, msg){ json(res, {ok:false, error:msg}); }
function body(req, cb){
  var b = "";
  req.on("data", function(d){ b += d; if(b.length > 4e6) req.destroy(); });
  req.on("end", function(){ try{ cb(b ? JSON.parse(b) : {}); }catch(e){ cb({}); } });
}
function clientIP(req){ return (req.headers["x-forwarded-for"]||"").split(",")[0].trim() || req.socket.remoteAddress || "?"; }
function checkToken(t){ var e = tokens[t]; return e && e > Date.now(); }
function needAdmin(s, t){ return checkToken(t); }

var server = http.createServer(function(req, res){
  var u = req.url.split("?")[0];
  var ip = clientIP(req);

  /* 静态资源 */
  if(u.indexOf("/api/") !== 0){
    var rel = u === "/" ? "/index.html" : u;
    var fp = path.join(ROOT, "public", rel.replace(/\.\./g, ""));
    if(!fs.existsSync(fp) || fs.statSync(fp).isDirectory()) fp = path.join(ROOT, "public", "index.html");
    try{
      var buf = fs.readFileSync(fp);
      send(res, 200, buf, MIME[path.extname(fp).toLowerCase()] || "application/octet-stream");
    }catch(e){ send(res, 404, "not found", "text/plain; charset=utf-8"); }
    return;
  }

  /* 健康检查 */
  if(u === "/api/health"){ json(res, {ok:true, season:curId(), time:nowISO()}); return; }

  /* 学生端启动配置：不含任何学生名单 */
  if(u === "/api/boot" && req.method === "GET"){
    var s = cur();
    json(res, {ok:true, seasonId:s.id, name:s.name, seasonLabel:s.name,
      win:winStateOf(s), winText:winText(s.window), window:s.window,
      classes:s.classes, subjects:s.subjects, notices:s.notices,
      srcNote:s.srcNote, paperNote:s.paperNote, serverTime:nowISO()});
    return;
  }

  /* 身份验证 */
  if(u === "/api/verify" && req.method === "POST"){
    body(req, function(b){
      var s = cur();
      var cls = String(b.cls||"").trim(), q = String(b.name||"").trim();
      var pool = (s.students||[]).filter(function(x){ return x.cls === cls; });
      var m = pool.filter(function(x){ return x.cn === q || upper(x.en).replace(/\s+/g,"") === upper(q).replace(/\s+/g,""); });
      if(m.length !== 1){ pushAlert(s, "", false, ip); putSeason(s); json(res, {code:"nomatch"}); return; }
      var st = merged(s, m[0].id);
      var nd = normDob(b.dob), ok = (nd === normDob(st.dob));
      pushAlert(s, st.id, ok, ip);
      var fm = failMap[ip] || {n:0, until:0};
      if(fm.until && fm.until > Date.now()){ putSeason(s); json(res, {code:"locked", until:fm.until, n:fm.n}); return; }

      if(ok){
        failMap[ip] = {n:0, until:0};
        putSeason(s);
        json(res, {code:"ok", sid:st.id, dob:st.dob, student:st,
          record:s.records[st.id]||null, ticket:s.tickets[st.id]||null});
        return;
      }
      /* 不匹配 */
      var rec = s.records[st.id];
      if(rec && !rec.unlocked){
        /* 已提交过：查看回执也必须通过本人验证，不放行 */
        var n2 = fm.n + 1, hit = n2 >= FAIL_MAX;
        failMap[ip] = hit ? {n:n2, until:Date.now()+FAIL_LOCK_MIN*60000} : {n:n2, until:0};
        putSeason(s);
        json(res, {code:"locked", n:n2, until:failMap[ip].until, masked:{cn:maskCn(st.cn), cls:st.cls, g:st.g}});
        return;
      }
      var old = s.tickets[st.id];
      if(old && old.status === "rejected"){
        putSeason(s);
        json(res, {code:"ok", sid:st.id, dob:st.dob, student:st, record:rec||null, ticket:old});
        return;
      }
      if(!b.nameOk){
        putSeason(s);
        json(res, {code:"nameCheck", sid:st.id, tryDob:nd, masked:{cn:maskCn(st.cn), cls:st.cls, g:st.g}});
        return;
      }
      var n3 = fm.n + 1, hit3 = n3 >= FAIL_MAX;
      failMap[ip] = hit3 ? {n:n3, until:Date.now()+FAIL_LOCK_MIN*60000} : {n:n3, until:0};
      var round = old ? (old.status === "wait" ? (old.round||1) : (old.round||0)+1) : 1;
      s.tickets[st.id] = {status:"wait", round:round, text:"出生日期验证不一致：本人填写 "+nd+"，学籍记录 "+st.dob+"。",
        at:nowISO(), auto:true, dobTry:nd, ip:ip};
      putSeason(s);
      json(res, {code:"ticket", sid:st.id, dob:st.dob, student:st, record:rec||null,
        ticket:s.tickets[st.id], fails:n3, until:failMap[ip].until});
    });
    return;
  }

  /* 学生端写回：只能写本人（sid + 出生日期双重校验） */
  if(u === "/api/push" && req.method === "POST"){
    body(req, function(b){
      var s = cur();
      var sid = String(b.sid||"");
      var st = merged(s, sid);
      if(!st || normDob(b.dob) !== normDob(st.dob)){ err(res, "身份校验未通过"); return; }
      if(winStateOf(s) === "closed" && !(b.record && b.record.unlocked)){ err(res, "窗口已关闭，不再受理提交"); return; }
      if(b.record){
        var tk = s.tickets[sid];
        if(tk && (tk.status === "wait" || tk.status === "fixed")){ err(res, "档案纠错未处理完毕，暂不能提交"); return; }
        var oldR = s.records[sid];
        b.record.sid = sid;
        b.record.ip = ip;
        b.record.modCount = oldR ? (oldR.modCount||0)+1 : 0;
        s.records[sid] = b.record;
      }
      if(b.ticket){ s.tickets[sid] = b.ticket; }
      putSeason(s);
      json(res, {ok:true, record:s.records[sid]||null, ticket:s.tickets[sid]||null});
    });
    return;
  }

  /* 教务登录 */
  if(u === "/api/admin/login" && req.method === "POST"){
    body(req, function(b){
      var a = readJSON(ADMINF, {pass:"exam2026"});
      if(String(b.pass||"") !== String(a.pass||"")){ err(res, "口令不正确"); return; }
      var t = crypto.randomBytes(16).toString("hex");
      tokens[t] = Date.now() + 8*3600*1000;
      json(res, {ok:true, token:t});
    });
    return;
  }
  if(u === "/api/admin/state" && req.method === "GET"){
    var tk2 = decodeURIComponent((req.url.split("token=")[1]||"").split("&")[0]);
    if(!checkToken(tk2)){ err(res, "未登录或登录已过期"); return; }
    var sc = cur();
    json(res, {ok:true, seasonId:sc.id, name:sc.name, seasonLabel:sc.name,
      win:winStateOf(sc), winText:winText(sc.window), window:sc.window,
      classes:sc.classes, subjects:sc.subjects, notices:sc.notices,
      srcNote:sc.srcNote, paperNote:sc.paperNote,
      students:sc.students, overrides:sc.overrides, records:sc.records,
      tickets:sc.tickets, alerts:sc.alerts||[], seasons:seasonList()});
    return;
  }
  if(u === "/api/admin/save" && req.method === "POST"){
    body(req, function(b){
      if(!checkToken(b.token)){ err(res, "未登录或登录已过期"); return; }
      var s2 = cur();
      if(b.records){ s2.records = b.records; }
      if(b.tickets){ s2.tickets = b.tickets; }
      if(b.overrides){ s2.overrides = b.overrides; }
      if(b.alerts){ s2.alerts = b.alerts; }
      putSeason(s2);
      json(res, {ok:true});
    });
    return;
  }
  /* 考试季管理与名单导入 */
  if(u === "/api/admin/season" && req.method === "POST"){
    body(req, function(b){
      if(!checkToken(b.token)){ err(res, "未登录或登录已过期"); return; }
      var act = b.action;
      if(act === "list"){ json(res, {ok:true, seasons:seasonList(), current:curId()}); return; }
      if(act === "switch"){
        if(!getSeason(b.id)){ err(res, "考试季不存在"); return; }
        writeJSON(IDX, {current:b.id});
        json(res, {ok:true, current:b.id});
        return;
      }
      if(act === "create"){
        var id = String(b.id||"").trim();
        if(!id){ err(res, "请填写考试季编号"); return; }
        if(getSeason(id)){ err(res, "该考试季编号已存在"); return; }
        var from = b.copyFrom ? getSeason(b.copyFrom) : cur();
        var ns = newSeason(id, b.name||id, b.start, b.end, b.classes||(from?from.classes:[]),
          from?from.subjects:SEED_SUBJECTS, from?from.notices:SEED_NOTICES.slice(),
          b.withRoster && from ? from.students.map(function(x){return Object.assign({},x);}) : []);
        putSeason(ns);
        writeJSON(IDX, {current:id});
        json(res, {ok:true, current:id, seasons:seasonList()});
        return;
      }
      if(act === "archive"){
        var s3 = getSeason(b.id); if(!s3){ err(res, "考试季不存在"); return; }
        s3.archived = true; s3.archivedAt = nowISO(); putSeason(s3);
        json(res, {ok:true, seasons:seasonList()});
        return;
      }
      if(act === "config"){
        var s4 = cur();
        if(b.name) s4.name = b.name;
        if(b.start) s4.window.start = b.start;
        if(b.end) s4.window.end = b.end;
        if(b.classes) s4.classes = b.classes;
        if(b.notices) s4.notices = b.notices;
        putSeason(s4);
        json(res, {ok:true, winText:winText(s4.window)});
        return;
      }
      if(act === "roster"){
        var s5 = cur();
        var has = Object.keys(s5.records||{}).length;
        if(has && !b.force){ err(res, "本季已有 "+has+" 条提交记录，整体替换名单会破坏已有记录。如确需重来，请先新建考试季。"); return; }
        var list = (b.students||[]).map(function(x){
          return {id:String(x.id||"").trim(), cls:String(x.cls||"").trim(), cn:String(x.cn||"").trim(),
            en:upper(x.en), g:String(x.g||"").trim(), dob:normDob(x.dob)};
        }).filter(function(x){ return x.id && x.cn; });
        s5.students = list; s5.rosterAt = nowISO();
        putSeason(s5);
        json(res, {ok:true, count:list.length, classes:Array.from(new Set(list.map(function(x){return x.cls}))) });
        return;
      }
      err(res, "未知操作");
    });
    return;
  }

  err(res, "未知接口 "+u);
});

server.listen(PORT, function(){
  console.log("------------------------------------------");
  console.log(" 学生报考系统已启动");
  console.log(" 本机访问： http://localhost:" + PORT);
  console.log(" 当前考试季：" + curId());
  console.log(" 教务后台口令：见 data/admin.json（默认 exam2026）");
  console.log("------------------------------------------");
});
