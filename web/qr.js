/* Minimal QR code generator for Nova AI (byte mode, error-correction level M, versions 1-10).
   No dependencies. Usage: const qr = NovaQR.make("text"); qr.size; qr.get(row, col) -> true/false
   NovaQR.draw(canvas, "text", pixelsPerModule) draws it with a white quiet zone. */
(function () {
  // [ecc codewords per block, [blocks, data codewords per block], ...] for level M
  const SPEC = {
    1: [10, [1, 16]], 2: [16, [1, 28]], 3: [26, [1, 44]], 4: [18, [2, 32]], 5: [24, [2, 43]],
    6: [16, [4, 27]], 7: [18, [4, 31]], 8: [22, [2, 38], [2, 39]], 9: [22, [3, 36], [2, 37]],
    10: [26, [4, 43], [1, 44]],
  };
  const ALIGN = { 1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50] };

  // ---- Galois field 256 (poly 0x11D) ----
  const EXP = new Array(512), LOG = new Array(256);
  (function () {
    let x = 1;
    for (let i = 0; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 256) x ^= 0x11d; }
    for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  })();
  const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);

  function rsGen(n) {
    let g = [1];
    for (let i = 0; i < n; i++) {
      const ng = new Array(g.length + 1).fill(0);
      for (let j = 0; j < g.length; j++) { ng[j] ^= g[j]; ng[j + 1] ^= mul(g[j], EXP[i]); }
      g = ng;
    }
    return g; // highest degree first
  }
  function rsRemainder(data, n) {
    const g = rsGen(n), res = new Array(n).fill(0);
    for (const d of data) {
      const f = d ^ res.shift(); res.push(0);
      if (f) for (let i = 0; i < n; i++) res[i] ^= mul(g[i + 1], f);
    }
    return res;
  }

  function utf8(str) { return Array.from(new TextEncoder().encode(str)); }

  function formatBits(mask) { // level M = 0b00
    const data = (0 << 3) | mask;
    let rem = data << 10;
    for (let i = 14; i >= 10; i--) if ((rem >> i) & 1) rem ^= 0x537 << (i - 10);
    return ((data << 10) | rem) ^ 0x5412;
  }
  function versionBits(ver) {
    let rem = ver << 12;
    for (let i = 17; i >= 12; i--) if ((rem >> i) & 1) rem ^= 0x1f25 << (i - 12);
    return (ver << 12) | rem;
  }

  function make(text) {
    const bytes = utf8(text);
    let ver = 0;
    for (let v = 1; v <= 10; v++) {
      const spec = SPEC[v];
      let dataCw = 0;
      for (let i = 1; i < spec.length; i++) dataCw += spec[i][0] * spec[i][1];
      const lenBits = v < 10 ? 8 : 16;
      if (4 + lenBits + bytes.length * 8 <= dataCw * 8) { ver = v; break; }
    }
    if (!ver) throw new Error("Text too long for QR");
    const spec = SPEC[ver], eccLen = spec[0];
    let dataCw = 0;
    for (let i = 1; i < spec.length; i++) dataCw += spec[i][0] * spec[i][1];

    // ---- bit stream ----
    const bits = [];
    const put = (val, n) => { for (let i = n - 1; i >= 0; i--) bits.push((val >> i) & 1); };
    put(0b0100, 4);
    put(bytes.length, ver < 10 ? 8 : 16);
    bytes.forEach((b) => put(b, 8));
    for (let i = 0; i < 4 && bits.length < dataCw * 8; i++) bits.push(0);
    while (bits.length % 8) bits.push(0);
    const cw = [];
    for (let i = 0; i < bits.length; i += 8) cw.push(parseInt(bits.slice(i, i + 8).join(""), 2));
    for (let p = 0; cw.length < dataCw; p ^= 1) cw.push(p ? 0x11 : 0xec);

    // ---- split into blocks, add ECC, interleave ----
    const blocks = [];
    let pos = 0;
    for (let i = 1; i < spec.length; i++) {
      for (let b = 0; b < spec[i][0]; b++) {
        const d = cw.slice(pos, pos + spec[i][1]); pos += spec[i][1];
        blocks.push({ d, e: rsRemainder(d, eccLen) });
      }
    }
    const out = [];
    const maxD = Math.max(...blocks.map((b) => b.d.length));
    for (let i = 0; i < maxD; i++) blocks.forEach((b) => { if (i < b.d.length) out.push(b.d[i]); });
    for (let i = 0; i < eccLen; i++) blocks.forEach((b) => out.push(b.e[i]));

    // ---- matrix ----
    const N = ver * 4 + 17;
    const m = Array.from({ length: N }, () => new Array(N).fill(false));
    const fn = Array.from({ length: N }, () => new Array(N).fill(false)); // function-pattern map
    const setF = (r, c, v) => { if (r >= 0 && c >= 0 && r < N && c < N) { m[r][c] = v; fn[r][c] = true; } };

    const finder = (r0, c0) => {
      for (let dr = -1; dr <= 7; dr++) for (let dc = -1; dc <= 7; dc++) {
        const inside = dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6;
        const dark = inside && (dr === 0 || dr === 6 || dc === 0 || dc === 6 || (dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4));
        setF(r0 + dr, c0 + dc, dark);
      }
    };
    finder(0, 0); finder(0, N - 7); finder(N - 7, 0);
    for (let i = 8; i < N - 8; i++) { setF(6, i, i % 2 === 0); setF(i, 6, i % 2 === 0); } // timing
    const al = ALIGN[ver];
    for (const r of al) for (const c of al) {
      if ((r === 6 && c === 6) || (r === 6 && c === al[al.length - 1]) || (r === al[al.length - 1] && c === 6)) continue;
      for (let dr = -2; dr <= 2; dr++) for (let dc = -2; dc <= 2; dc++)
        setF(r + dr, c + dc, Math.max(Math.abs(dr), Math.abs(dc)) !== 1);
    }
    setF(N - 8, 8, true); // dark module
    // reserve format areas
    for (let i = 0; i < 9; i++) { if (!fn[8][i]) setF(8, i, false); if (!fn[i][8]) setF(i, 8, false); }
    for (let i = 0; i < 8; i++) { setF(8, N - 1 - i, false); setF(N - 1 - i, 8, false); }
    setF(N - 8, 8, true);
    if (ver >= 7) { // version info
      const vb = versionBits(ver);
      for (let i = 0; i < 18; i++) {
        const bit = ((vb >> i) & 1) === 1, a = Math.floor(i / 3), b = (i % 3) + N - 11;
        setF(a, b, bit); setF(b, a, bit);
      }
    }

    // ---- place data (zig-zag) ----
    const dataBits = [];
    out.forEach((b) => { for (let i = 7; i >= 0; i--) dataBits.push((b >> i) & 1); });
    const place = (maskFn) => {
      const g = m.map((row) => row.slice());
      let idx = 0, up = true;
      for (let col = N - 1; col > 0; col -= 2) {
        if (col === 6) col--;
        for (let k = 0; k < N; k++) {
          const r = up ? N - 1 - k : k;
          for (let dc = 0; dc < 2; dc++) {
            const c = col - dc;
            if (fn[r][c]) continue;
            let bit = idx < dataBits.length ? dataBits[idx] === 1 : false; idx++;
            if (maskFn(r, c)) bit = !bit;
            g[r][c] = bit;
          }
        }
        up = !up;
      }
      return g;
    };
    const MASKS = [
      (r, c) => (r + c) % 2 === 0, (r) => r % 2 === 0, (r, c) => c % 3 === 0, (r, c) => (r + c) % 3 === 0,
      (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0, (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
      (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0, (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
    ];
    const withFormat = (g, mask) => {
      const f = formatBits(mask), h = g.map((row) => row.slice());
      const bit = (i) => ((f >> i) & 1) === 1;
      for (let i = 0; i <= 5; i++) h[i][8] = bit(i);
      h[7][8] = bit(6); h[8][8] = bit(7); h[8][7] = bit(8);
      for (let i = 9; i < 15; i++) h[8][14 - i] = bit(i);
      for (let i = 0; i < 8; i++) h[8][N - 1 - i] = bit(i);
      for (let i = 8; i < 15; i++) h[N - 15 + i][8] = bit(i);
      h[N - 8][8] = true;
      return h;
    };
    const penalty = (g) => {
      let p = 0;
      for (let pass = 0; pass < 2; pass++) { // rows then columns
        for (let a = 0; a < N; a++) {
          let run = 1;
          for (let b = 1; b < N; b++) {
            const cur = pass ? g[b][a] : g[a][b], prev = pass ? g[b - 1][a] : g[a][b - 1];
            if (cur === prev) { run++; if (run === 5) p += 3; else if (run > 5) p++; } else run = 1;
          }
          const line = []; for (let b = 0; b < N; b++) line.push(pass ? g[b][a] : g[a][b]);
          const s = line.map((x) => (x ? 1 : 0)).join("");
          const pats = ["10111010000", "00001011101"];
          for (const pt of pats) { let i = -1; while ((i = s.indexOf(pt, i + 1)) !== -1) p += 40; }
        }
      }
      for (let r = 0; r < N - 1; r++) for (let c = 0; c < N - 1; c++)
        if (g[r][c] === g[r][c + 1] && g[r][c] === g[r + 1][c] && g[r][c] === g[r + 1][c + 1]) p += 3;
      let dark = 0; g.forEach((row) => row.forEach((x) => { if (x) dark++; }));
      p += Math.floor(Math.abs((dark * 100) / (N * N) - 50) / 5) * 10;
      return p;
    };
    let best = null, bestP = Infinity;
    for (let k = 0; k < 8; k++) {
      const g = withFormat(place(MASKS[k]), k), p = penalty(g);
      if (p < bestP) { bestP = p; best = g; }
    }
    return { size: N, version: ver, get: (r, c) => best[r][c] };
  }

  function draw(canvas, text, scale) {
    const qr = make(text), q = 4, s = scale || 6, n = (qr.size + q * 2) * s;
    canvas.width = canvas.height = n;
    const g = canvas.getContext("2d");
    g.fillStyle = "#fff"; g.fillRect(0, 0, n, n);
    g.fillStyle = "#000";
    for (let r = 0; r < qr.size; r++) for (let c = 0; c < qr.size; c++)
      if (qr.get(r, c)) g.fillRect((c + q) * s, (r + q) * s, s, s);
    return qr;
  }

  window.NovaQR = { make, draw };
})();
