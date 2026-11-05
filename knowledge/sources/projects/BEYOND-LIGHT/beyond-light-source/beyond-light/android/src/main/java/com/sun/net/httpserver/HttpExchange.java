package com.sun.net.httpserver;

import java.io.*;
import java.net.URI;
import java.net.Socket;

public final class HttpExchange implements AutoCloseable {
    private final Socket socket;
    private final String method;
    private final URI uri;
    private final Headers requestHeaders;
    private final Headers responseHeaders = new Headers();
    private final InputStream requestBody;
    private final OutputStream responseBody;
    private boolean headersSent;

    HttpExchange(Socket socket, String method, URI uri, Headers headers, byte[] body) throws IOException {
        this.socket = socket; this.method = method; this.uri = uri; this.requestHeaders = headers;
        this.requestBody = new ByteArrayInputStream(body);
        this.responseBody = socket.getOutputStream();
    }
    public String getRequestMethod() { return method; }
    public URI getRequestURI() { return uri; }
    public Headers getRequestHeaders() { return requestHeaders; }
    public Headers getResponseHeaders() { return responseHeaders; }
    public InputStream getRequestBody() { return requestBody; }
    public OutputStream getResponseBody() { return responseBody; }
    public void sendResponseHeaders(int status, long length) throws IOException {
        if (headersSent) throw new IOException("response already started");
        headersSent = true;
        String reason = switch (status) { case 200 -> "OK"; case 204 -> "No Content"; case 400 -> "Bad Request"; case 404 -> "Not Found"; case 413 -> "Payload Too Large"; case 500 -> "Internal Server Error"; default -> "Response"; };
        if (responseHeaders.getFirst("Content-Type") == null) responseHeaders.set("Content-Type", "text/plain; charset=utf-8");
        responseHeaders.set("Content-Length", Long.toString(Math.max(0, length)));
        responseHeaders.set("Connection", "close");
        StringBuilder out = new StringBuilder("HTTP/1.1 ").append(status).append(' ').append(reason).append("\r\n");
        for (var e : responseHeaders.entrySet()) for (String v : e.getValue()) out.append(e.getKey()).append(": ").append(v).append("\r\n");
        out.append("\r\n"); responseBody.write(out.toString().getBytes(java.nio.charset.StandardCharsets.ISO_8859_1)); responseBody.flush();
    }
    @Override public void close() throws IOException { try { requestBody.close(); } finally { socket.close(); } }
}
