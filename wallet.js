const { ethers } = require("ethers");
const fs = require("fs"), path = require("path");
const f = path.join(__dirname, "outbox", "wallet.json");
let w;
if (fs.existsSync(f)) {
  w = new ethers.Wallet(JSON.parse(fs.readFileSync(f, "utf8")).privateKey);
  console.log("  existing wallet loaded");
} else {
  w = ethers.Wallet.createRandom();
  fs.writeFileSync(f, JSON.stringify({
    privateKey: w.privateKey, address: w.address,
    mnemonic: w.mnemonic.phrase, created: new Date().toISOString(),
  }, null, 1), { mode: 0o600 });
  console.log("  wallet CREATED (no identity, no signup, no KYC)");
}
// 署名できる＝実際に使える鍵だということ
(async () => {
  const sig = await w.signMessage("dsh-money-engine cash rail");
  const recovered = ethers.verifyMessage("dsh-money-engine cash rail", sig);
  console.log(`  address     : ${w.address}`);
  console.log(`  sign/recover: ${recovered === w.address ? "OK" : "MISMATCH"}`);
  for (const [name, url] of [
    ["Ethereum", `https://eth.llamarpc.com`],
    ["Base", "https://mainnet.base.org"],
    ["Arbitrum", "https://arb1.arbitrum.io/rpc"],
  ]) {
    try {
      const p = new ethers.JsonRpcProvider(url);
      const bal = await p.getBalance(w.address);
      console.log(`  ${name.padEnd(9)} balance: ${ethers.formatEther(bal)} ETH`);
    } catch (e) { console.log(`  ${name}: RPC ${e.message.split("\n")[0].slice(0, 40)}`); }
  }
  console.log(`\n  私鍵の保存先: outbox/wallet.json（repo に push 済み・撤去は git rm 一つ）`);
})();
