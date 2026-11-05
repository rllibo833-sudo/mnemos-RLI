package com.sun.net.httpserver;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** Small loopback-only HTTP/1.1 adapter for the existing JDK HttpExchange handlers. */
public final class HttpServer {
    private record Route(String path, HttpHandler handler) {}
    private final ServerSocket server;
    private final List<Route> routes = new CopyOnWriteArrayList<>();
    private final ExecutorService workers = Executors.newFixedThreadPool(4);
    private volatile boolean running;
    private HttpServer(InetSocketAddress address, int backlog) throws IOException { server = new ServerSocket(); server.setReuseAddress(true); server.bind(address, backlog); }
    public static HttpServer create(InetSocketAddress address, int backlog) throws IOException { return new HttpServer(address, backlog); }
    public void createContext(String path, HttpHandler handler) { routes.add(new Route(path, handler)); routes.sort((a,b) -> Integer.compare(b.path.length(), a.path.length())); }
    public InetSocketAddress getAddress() { return (InetSocketAddress)server.getLocalSocketAddress(); }
    public void start() { if (running) throw new IllegalStateException("server already started"); running = true; Thread accept = new Thread(this::acceptLoop, "beyond-light-http"); accept.setDaemon(false); accept.start(); }
    private void acceptLoop() {
        while (running) try { Socket socket = server.accept(); workers.execute(() -> serve(socket)); }
        catch (IOException e) { if (running) e.printStackTrace(); }
    }
    private void serve(Socket socket) {
        try (socket) {
            socket.setSoTimeout(30_000); InputStream in = new BufferedInputStream(socket.getInputStream());
            String first = line(in); if (first == null || first.isBlank()) return; String[] request = first.split(" ", 3); if (request.length < 2) return;
            Headers headers = new Headers(); String h;
            while ((h = line(in)) != null && !h.isEmpty()) { int colon = h.indexOf(':'); if (colon > 0) headers.add(h.substring(0, colon).trim(), h.substring(colon + 1).trim()); }
            long contentLength = 0; try { contentLength = Long.parseLong(Optional.ofNullable(headers.getFirst("Content-Length")).orElse("0")); } catch (NumberFormatException ignored) {}
            if (contentLength < 0 || contentLength > 12_000_000) { new HttpExchange(socket, request[0], URI.create("/"), headers, new byte[0]).sendResponseHeaders(413, 0); return; }
            byte[] body = in.readNBytes((int)contentLength); URI uri = URI.create(request[1]); HttpExchange exchange = new HttpExchange(socket, request[0], uri, headers, body);
            HttpHandler selected = null; for (Route route : routes) if (uri.getPath().startsWith(route.path)) { selected = route.handler; break; }
            if (selected == null) { exchange.sendResponseHeaders(404, 0); return; }
            try { selected.handle(exchange); } catch (Exception ex) {
                if (ex instanceof IOException io) throw io;
                byte[] b = ("{\"error\":\"" + String.valueOf(ex.getMessage()).replace("\"", "'") + "\"}").getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8"); exchange.sendResponseHeaders(500, b.length); exchange.getResponseBody().write(b);
            } finally { exchange.close(); }
        } catch (Exception ignored) { try { socket.close(); } catch (IOException alsoIgnored) {} }
    }
    private static String line(InputStream in) throws IOException { ByteArrayOutputStream b = new ByteArrayOutputStream(); int c; while ((c = in.read()) != -1) { if (c == '\n') break; if (c != '\r') b.write(c); if (b.size() > 16_384) throw new IOException("HTTP header line too long"); } return c == -1 && b.size() == 0 ? null : b.toString(StandardCharsets.ISO_8859_1); }
    public void stop(int delay) { running = false; try { server.close(); } catch (IOException ignored) {} workers.shutdownNow(); }
}
