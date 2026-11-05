package org.beyondlight.android;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.DownloadListener;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;
import org.beyondlight.Main;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.file.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Offline WebView host. The existing Main handlers and all science engines remain the API/core. */
public final class MainActivity extends Activity {
    private static final int SAVE_FILE = 841;
    private static final int OPEN_FILE = 842;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private WebView web;
    private TextView status;
    private String pendingDownloadUrl;
    private android.webkit.ValueCallback<Uri[]> filePicker;
    private String pendingDownloadName = "beyond-light-export.json";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(12,18,25));
        getWindow().setNavigationBarColor(Color.rgb(12,18,25));
        Path data = getFilesDir().toPath().resolve("data");
        try { Files.createDirectories(data); seedIfAbsent("data/experiments.jsonl", data.resolve("experiments.jsonl")); seedIfAbsent("data/benchmarks.jsonl", data.resolve("benchmarks.jsonl")); seedIfAbsent("data/materials.jsonl", data.resolve("materials.jsonl")); seedIfAbsent("data/published_experiments.jsonl", data.resolve("published_experiments.jsonl")); seedIfAbsent("data/material_curves.jsonl", data.resolve("material_curves.jsonl")); }
        catch (IOException e) { showFatal("Penyimpanan lokal tidak dapat disiapkan: " + e.getMessage()); return; }
        System.setProperty("beyondlight.dataDir", getFilesDir().getAbsolutePath());

        FrameLayout root = new FrameLayout(this); root.setBackgroundColor(Color.rgb(12,18,25));
        web = new WebView(this); status = new TextView(this); status.setTextColor(Color.WHITE); status.setText("Menyiapkan laboratorium offline…"); status.setPadding(24,32,24,24);
        root.addView(web, new FrameLayout.LayoutParams(-1,-1)); root.addView(status, new FrameLayout.LayoutParams(-1,-2)); setContentView(root);
        configureWebView();
        io.execute(() -> startBackend());
    }

    private void seedIfAbsent(String asset, Path target) throws IOException {
        if (Files.exists(target)) return;
        try (InputStream in = getAssets().open(asset); OutputStream out = Files.newOutputStream(target, StandardOpenOption.CREATE_NEW)) { in.transferTo(out); }
    }

    private void startBackend() {
        Thread server = new Thread(() -> { try { Main.main(new String[]{"0"}); } catch (Exception e) { ui.post(() -> showFatal("Layanan lokal gagal berjalan: " + e.getMessage())); } }, "beyond-light-engine");
        server.setDaemon(true); server.start();
        long end = System.currentTimeMillis() + 15_000;
        while (Main.BOUND_PORT < 0 && System.currentTimeMillis() < end) try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
        if (Main.BOUND_PORT < 0) { ui.post(() -> showFatal("Layanan perhitungan tidak merespons.")); return; }
        int port = Main.BOUND_PORT;
        ui.post(() -> { if (isFinishing() || web == null) return; status.setVisibility(View.GONE); web.loadUrl("http://127.0.0.1:" + port + "/"); });
    }

    private void configureWebView() {
        WebSettings settings = web.getSettings(); settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false); settings.setAllowContentAccess(true); settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW); settings.setSafeBrowsingEnabled(true);
        web.setBackgroundColor(Color.rgb(12,18,25)); web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if ("127.0.0.1".equals(u.getHost()) && u.getPort() == Main.BOUND_PORT) return false;
                if ("https".equalsIgnoreCase(u.getScheme())) { try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) {} return true; }
                return true;
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, android.webkit.WebResourceError error) {
                if (request.isForMainFrame()) ui.post(() -> { if (status != null) { status.setText("Halaman lokal gagal dibuka. Tutup lalu buka kembali aplikasi."); status.setVisibility(View.VISIBLE); } });
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, android.webkit.ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (filePicker != null) filePicker.onReceiveValue(null); filePicker = callback;
                Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT); i.addCategory(Intent.CATEGORY_OPENABLE); i.setType("*/*");
                try { startActivityForResult(i, OPEN_FILE); return true; } catch (Exception e) { filePicker = null; callback.onReceiveValue(null); return false; }
            }
        });
        web.setDownloadListener((url, agent, disposition, type, length) -> beginSave(url, disposition, type));
    }

    private void beginSave(String url, String disposition, String type) {
        if (!url.startsWith("http://127.0.0.1:" + Main.BOUND_PORT + "/")) { Toast.makeText(this, "Hanya ekspor lokal yang didukung.", Toast.LENGTH_SHORT).show(); return; }
        pendingDownloadUrl = url; pendingDownloadName = disposition != null && disposition.contains("filename=") ? disposition.substring(disposition.indexOf("filename=") + 9).replace("\"", "") : "beyond-light-export.json";
        Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT); i.addCategory(Intent.CATEGORY_OPENABLE); i.setType(type == null ? "application/octet-stream" : type); i.putExtra(Intent.EXTRA_TITLE, pendingDownloadName); startActivityForResult(i, SAVE_FILE);
    }

    private void transferDownload(Uri target) {
        try {
            HttpURLConnection c = (HttpURLConnection)new URL(pendingDownloadUrl).openConnection(); c.setConnectTimeout(5000); c.setReadTimeout(30000);
            try (InputStream in = c.getInputStream(); OutputStream out = getContentResolver().openOutputStream(target, "w")) { if (out == null) throw new IOException("destination unavailable"); in.transferTo(out); }
            ui.post(() -> Toast.makeText(this, "Laporan tersimpan pada lokasi yang dipilih.", Toast.LENGTH_LONG).show());
        } catch (Exception e) { ui.post(() -> Toast.makeText(this, "Ekspor gagal: " + e.getMessage(), Toast.LENGTH_LONG).show()); }
        finally { pendingDownloadUrl = null; }
    }

    private void showFatal(String message) { if (status == null) { TextView t = new TextView(this); t.setTextColor(Color.WHITE); t.setText(message); setContentView(t); } else { status.setText(message); status.setVisibility(View.VISIBLE); } }
    @Override public void onBackPressed() { if (web != null && web.canGoBack()) web.goBack(); else super.onBackPressed(); }
    @Override protected void onDestroy() { if (web != null) { web.stopLoading(); web.destroy(); web = null; } io.shutdownNow(); Main.stopServer(); super.onDestroy(); }
}
