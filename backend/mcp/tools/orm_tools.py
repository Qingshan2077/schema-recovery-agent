"""ORM parser tools."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from backend.mcp.tool_registry import ToolRegistry


def parse_mybatis_xml(xml_content: str, file_name: str):
    relations = []
    ns_match = re.search(r'namespace="([^"]+)"', xml_content)
    namespace = ns_match.group(1) if ns_match else "unknown"

    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        root = ET.fromstring(xml_content, parser=parser)
        for assoc in root.iter("association"):
            relations.append(
                {
                    "type": "association",
                    "property": assoc.attrib.get("property", ""),
                    "java_type": assoc.attrib.get("javaType", ""),
                    "column": assoc.attrib.get("column", ""),
                    "select_method": assoc.attrib.get("select", "(inline)"),
                    "source_file": file_name,
                }
            )
        for coll in root.iter("collection"):
            relations.append(
                {
                    "type": "collection",
                    "property": coll.attrib.get("property", ""),
                    "of_type": coll.attrib.get("ofType", ""),
                    "column": coll.attrib.get("column", ""),
                    "select_method": coll.attrib.get("select", "(inline)"),
                    "source_file": file_name,
                }
            )
    except ET.ParseError:
        assoc_pattern = re.compile(r"<association\s+([^>]*)/?>", re.IGNORECASE)
        coll_pattern = re.compile(r"<collection\s+([^>]*)/?>", re.IGNORECASE)
        for attrs in assoc_pattern.findall(xml_content):
            relations.append({"type": "association", **_parse_attrs(attrs), "source_file": file_name})
        for attrs in coll_pattern.findall(xml_content):
            relations.append({"type": "collection", **_parse_attrs(attrs), "source_file": file_name})

    column_mappings = re.findall(r'<(?:id|result)\s+property="(\w+)"\s+column="(\w+)"', xml_content)
    return {
        "namespace": namespace,
        "file": file_name,
        "relation_count": len(relations),
        "relations": relations,
        "column_count": len(column_mappings),
        "column_mappings": column_mappings,
    }


def _parse_attrs(attr_string: str) -> dict:
    return {k: v for k, v in re.findall(r'(\w+)="([^"]*)"', attr_string)}


def parse_jpa_annotations(java_content: str, file_name: str):
    return {
        "file": file_name,
        "has_annotations": "@ManyToOne" in java_content or "@OneToMany" in java_content,
        "message": "JPA parsing is not implemented; project primarily uses MyBatis",
        "relations": [],
    }


def register_all(registry: ToolRegistry):
    registry.register("parse_mybatis_xml", parse_mybatis_xml, "Parse MyBatis XML")
    registry.register("parse_jpa_annotations", parse_jpa_annotations, "Parse JPA annotations")

