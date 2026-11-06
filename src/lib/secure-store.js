/* 静态数据加密存储（仅用 Node 内置模块）
   AES-256-GCM，密文格式： EXAMENC1:<base64(iv | authTag | ciphertext)>

   密钥来源优先级：
     1. 环境变量 EXAM_DATA_KEY（32 字节的 base64 或 64 位 hex）—— 适合云部署
     2. <dataDir>/.key —— 首次启动自动生成，必须备份且不上传仓库
   设置 EXAM_PLAINTEXT=1 可临时退回明文（仅用于迁移排错，不建议生产使用）。

   兼容：readJSON 可读旧版明文文件；启动时 migrateAll() 会把残留明文统一加密。 */
var fs = require("fs"), path = require("path"), crypto = require("crypto");

var PREFIX = "EXAMENC1:";

function mkdirp(p){ if(!fs.existsSync(p)) fs.mkdirSync(p, {recursive:true}); }

function keyFromEnv(v){
  if(!v) return null;
  var b = Buffer.from(v, "base64");
  if(b.length === 32) return b;
  var h = Buffer.from(v, "hex");
  if(h.length === 32) return h;
  throw new Error("EXAM_DATA_KEY 无效：需要 32 字节密钥的 base64 或 64 位 hex");
}

module.exports = function createStore(dataDir, opts){
  opts = opts || {};
  mkdirp(dataDir);
  var keyPath = path.join(dataDir, ".key");
  var key = null, source = "";

  if(process.env.EXAM_PLAINTEXT === "1"){
    source = "plaintext(opted-out)";
  }else{
    key = keyFromEnv(process.env.EXAM_DATA_KEY);
    if(key){
      source = "env:EXAM_DATA_KEY";
    }else if(fs.existsSync(keyPath)){
      key = Buffer.from(fs.readFileSync(keyPath, "utf8").trim(), "base64");
      if(key.length !== 32) throw new Error("密钥文件损坏：" + keyPath);
      source = "file:" + keyPath;
    }else{
      if(opts.createKey === false)
        throw new Error("未找到数据密钥 " + keyPath + "，请先启动一次服务生成，或设置 EXAM_DATA_KEY");
      key = crypto.randomBytes(32);
      fs.writeFileSync(keyPath, key.toString("base64") + "\n", {encoding:"utf8", mode:0o600});
      source = "generated:" + keyPath;
    }
  }

  function encrypt(text){
    if(!key) return text;
    var iv = crypto.randomBytes(12);
    var c = crypto.createCipheriv("aes-256-gcm", key, iv);
    var body = Buffer.concat([c.update(text, "utf8"), c.final()]);
    return PREFIX + Buffer.concat([iv, c.getAuthTag(), body]).toString("base64");
  }
  function decrypt(raw){
    var buf = Buffer.from(raw.slice(PREFIX.length), "base64");
    var iv = buf.subarray(0, 12), tag = buf.subarray(12, 28), body = buf.subarray(28);
    var d = crypto.createDecipheriv("aes-256-gcm", key, iv);
    d.setAuthTag(tag);
    return Buffer.concat([d.update(body), d.final()]).toString("utf8");
  }
  function readJSON(p, def){
    try{
      var raw = fs.readFileSync(p, "utf8");
      if(raw.slice(0, PREFIX.length) === PREFIX){
        if(!key) throw new Error("存在加密数据但未配置密钥");
        return JSON.parse(decrypt(raw));
      }
      return JSON.parse(raw);            // 兼容旧版明文
    }catch(e){ return def; }
  }
  function writeJSON(p, o){
    mkdirp(path.dirname(p));
    /* 原子替换：先写临时文件再 rename，避免写入中断留下半截密文；
       同名临时文件带进程号与随机数，多进程并发时也不会互相踩踏。 */
    var tmp = p + ".tmp-" + process.pid + "-" + crypto.randomBytes(4).toString("hex");
    try{
      fs.writeFileSync(tmp, encrypt(JSON.stringify(o, null, 2)), {encoding:"utf8", mode:0o600});
      fs.renameSync(tmp, p);
    }catch(e){
      try{ fs.unlinkSync(tmp); }catch(_){}
      throw e;
    }
  }
  function isPlain(p){
    try{ return fs.readFileSync(p, "utf8").slice(0, PREFIX.length) !== PREFIX; }
    catch(e){ return false; }
  }
  /* 把历史明文数据一次性加密；返回被转换的文件数 */
  function migrateAll(){
    if(!key) return 0;
    var n = 0;
    function walk(dir){
      fs.readdirSync(dir).forEach(function(f){
        var p = path.join(dir, f);
        var st = fs.statSync(p);
        if(st.isDirectory()){ walk(p); return; }
        if(!/\.json$/i.test(f) || !isPlain(p)) return;
        var o = JSON.parse(fs.readFileSync(p, "utf8"));
        writeJSON(p, o);
        n++;
      });
    }
    walk(dataDir);
    return n;
  }
  return {readJSON:readJSON, writeJSON:writeJSON, migrateAll:migrateAll,
    keyPath:keyPath, keySource:source, encrypted:!!key};
};
