/* 修改教务后台口令
   数据文件已加密，不能再直接编辑 data/admin.json。
   用法： node tools/set-password.js <新口令>          （在 src/ 目录下执行）
   改完需重启服务（口令每次登录时从加密文件读取，实际即时生效，但建议重启确认）。 */
var fs = require("fs"), path = require("path");
var dataDir = path.join(__dirname, "..", "data");
var adminFile = path.join(dataDir, "admin.json");
var pass = process.argv[2];

if(!pass){
  console.error("用法： node tools/set-password.js <新口令>");
  process.exit(1);
}
if(pass.length < 8){
  console.error("口令至少 8 位，请换一个更长的。");
  process.exit(1);
}
var store = require("../lib/secure-store")(dataDir, {createKey:false});
var a = store.readJSON(adminFile, {pass:"exam2026"});
a.pass = pass;
store.writeJSON(adminFile, a);
console.log("已更新教务后台口令。");
console.log("密钥：" + store.keySource + "（请备份；丢失将无法解密学生数据）");
