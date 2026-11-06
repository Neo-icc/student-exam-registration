/* 整季加密备份 / 恢复（仅用 Node 内置模块）
   设计要点：
   - 备份文件本身是 AES-256-GCM 密文，密钥由「教务输入的备份口令」经 scrypt 派生，
     不依赖 data/.key。因此云端容器重建、密钥更换后仍可恢复到任意新环境。
   - 备份口令不落盘、不写日志；忘记口令 = 备份不可恢复。
   - 恢复前做格式、版本、认证标签与考试季结构校验，任一失败都不写入磁盘。 */
var crypto = require("crypto");
var FORMAT = "EXAMBAK1";

function derive(pass, salt){
  return crypto.scryptSync(String(pass), salt, 32, {N:16384, r:8, p:1, maxmem:64*1024*1024});
}

/* 把一个考试季对象封装成可下载的密文文本 */
function seal(season, pass){
  if(!pass || String(pass).length < 8) throw new Error("备份口令至少 8 位");
  var salt = crypto.randomBytes(16), iv = crypto.randomBytes(12);
  var c = crypto.createCipheriv("aes-256-gcm", derive(pass, salt), iv);
  var data = Buffer.concat([c.update(JSON.stringify(season), "utf8"), c.final()]);
  var pack = {v:1, fmt:FORMAT, at:new Date().toISOString(), seasonId:season.id,
    salt:salt.toString("base64"), iv:iv.toString("base64"),
    tag:c.getAuthTag().toString("base64"), data:data.toString("base64")};
  var text = FORMAT + ":" + Buffer.from(JSON.stringify(pack), "utf8").toString("base64");
  return {text:text, checksum:crypto.createHash("sha256").update(text).digest("hex"), at:pack.at};
}

/* 解开备份；口令错误 / 文件被篡改都会抛错（GCM 认证标签保证） */
function open(text, pass){
  var head = FORMAT + ":";
  if(String(text||"").slice(0, head.length) !== head) throw new Error("不是有效的加密备份文件");
  var pack;
  try{ pack = JSON.parse(Buffer.from(String(text).slice(head.length), "base64").toString("utf8")); }
  catch(e){ throw new Error("备份文件已损坏"); }
  if(pack.fmt !== FORMAT || pack.v !== 1) throw new Error("备份版本不受支持");
  try{
    var d = crypto.createDecipheriv("aes-256-gcm", derive(pass, Buffer.from(pack.salt, "base64")),
      Buffer.from(pack.iv, "base64"));
    d.setAuthTag(Buffer.from(pack.tag, "base64"));
    var obj = JSON.parse(Buffer.concat([d.update(Buffer.from(pack.data, "base64")), d.final()]).toString("utf8"));
    return {obj:obj, at:pack.at, seasonId:pack.seasonId};
  }catch(e){ throw new Error("备份口令不正确或文件已被篡改"); }
}

/* 恢复前的结构校验：拒绝把任意 JSON 写进数据目录 */
function validSeason(o){
  return !!(o && typeof o === "object" && typeof o.id === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(o.id)
    && o.window && typeof o.window === "object"
    && Array.isArray(o.students) && Array.isArray(o.classes)
    && o.records && typeof o.records === "object" && !Array.isArray(o.records)
    && o.tickets && typeof o.tickets === "object" && !Array.isArray(o.tickets));
}

module.exports = {seal:seal, open:open, validSeason:validSeason, FORMAT:FORMAT};
