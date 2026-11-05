# BEYOND-LIGHT

**Website:** https://rllibo833-sudo.github.io/Beyond-Light/

Beyond-Light adalah ruang eksplorasi pengetahuan ilmiah dan ide teknologi yang berjalan sebagai aplikasi **statis di browser**. Runtime website terdiri dari HTML, CSS, JavaScript, serta data publik JSONL/CSV. Tidak membutuhkan SnapDeploy, container, Node.js server, Java server, database server, atau secret key untuk membuka dan memakai fitur browser yang tersedia.

## Arsitektur runtime

| Bagian | Runtime | Keterangan |
|---|---|---|
| Antarmuka dan navigasi | Browser | `docs/index.html` |
| Mesin matematika, fisika, engineering, dan riset | Browser JavaScript | `docs/engine/` |
| Knowledge graph | Browser, read-only | Membaca branch publik `mnemos-RLI/Knowledge` secara langsung |
| Data ilmiah bawaan | Browser | File publik di `docs/data/` |
| Preferensi dan persamaan pengguna | Browser lokal | `localStorage` dan import/export file |
| Java source dan regression checks | Source/test reference | Bukan dependency runtime website |
| Android adapter | Android source terpisah | Bukan dependency website |

## Knowledge source

Website membaca manifest, node, dan edge dari:

`https://raw.githubusercontent.com/rllibo833-sudo/mnemos-RLI/Knowledge/knowledge/`

Integrasi ini read-only, tanpa token GitHub dan tanpa proxy server. Karena sumbernya publik, data Knowledge yang dibaca browser juga harus dianggap publik. Ketersediaan retrieval bergantung pada GitHub Raw dan kebijakan CORS browser.

## Batas kemampuan

- Mesin browser menjalankan operasi yang tercatat di `docs/catalog.json`; beberapa port Java masih parsial atau dibatasi.
- Pencarian graph adalah lexical matching, bukan semantic/vector search.
- Impor dataset memakai file lokal dan penyimpanan browser; tidak ada sinkronisasi akun/server.
- Hasil hitungan, screening engineering, dan benchmark bukan bukti eksperimen atau sertifikasi desain.
- Katalog internal mencatat hubungan source Java dengan implementasi browser. Status parsial tidak boleh dianggap setara penuh.

## Pengembangan dan pengujian

Website dapat dibuka langsung melalui GitHub Pages atau dari file statis lokal. Untuk menguji engine browser, gunakan Node.js hanya sebagai **test runner**, bukan server aplikasi:

```sh
node docs/engine/symbolic.test.cjs
node docs/engine/research.test.cjs
node docs/engine/decision.test.cjs
node docs/engine/feasibility.test.cjs
node docs/engine/feasibility-assessment.test.cjs
node docs/engine/technology-design.test.cjs
node docs/engine/research-core.test.cjs
```

Java 21 source dipertahankan sebagai referensi implementasi dan regression checks bagi port browser. Tidak ada Dockerfile atau perintah deployment container untuk aplikasi Java. Regression suite Java dapat dijalankan dari direktori `beyond-light-source/beyond-light` dengan `./check.sh`.

## Repository map

| Path | Fungsi |
|---|---|
| `docs/` | Website statis, browser engines, data publik, dan dokumentasi |
| `docs/engine/` | Mesin JavaScript dan regression tests |
| `docs/data/` | Dataset dan katalog publik |
| `beyond-light-source/beyond-light/src/main/java/` | Referensi source Java untuk audit dan porting |
| `beyond-light-source/beyond-light/src/test/` | Regression checks Java |
| `beyond-light-source/beyond-light/android/` | Source adapter Android eksperimental |
| `.github/workflows/pages.yml` | Validasi dan publikasi website statis GitHub Pages |

## Prinsip perubahan

1. Website tidak boleh bergantung pada endpoint localhost atau server Beyond-Light.
2. Tidak ada secret, private key, atau token di folder `docs/`.
3. Port browser harus memiliki regression tests dan status coverage yang jujur di `docs/catalog.json`.
4. Jangan menghapus source referensi sebelum pengganti browser diuji.
5. Keberhasilan build tidak membuktikan validitas eksperimen atau kelayakan engineering.

## License

Project saat ini all rights reserved. Baca [LICENSE](LICENSE) sebelum menyalin, memodifikasi, atau mendistribusikan isi repository.
