package com.codecontextgraph.cobol.json;

public record EntityJson(
    String kind, String qualifiedName, String simpleName,
    String filePath, int startLine, int endLine, boolean isExternal) {}
