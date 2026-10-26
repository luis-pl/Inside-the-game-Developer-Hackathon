"""Comunicación A2A entre agentes (a2a-sdk 1.2.x, JSON-RPC).

Los contratos viajan como JSON en partes de texto `application/json`: un
DataPart se transporta como google.protobuf.Value y convierte los enteros en
double, lo que rompería los IDs estrictos. Ver tests/test_a2a_transport.py.
"""
