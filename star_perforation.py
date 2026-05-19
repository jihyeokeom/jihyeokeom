# -*- coding: utf-8 -*-
"""
Rhino 6 - 별 모양 타공 스크립트
면(Surface) 또는 솔리드 오브젝트에 10mm 별 모양 구멍을 격자 배열로 뚫습니다.

사용법:
  1. Rhino 6 실행
  2. Tools > PythonScript > Edit 에서 이 스크립트를 붙여넣기
  3. Run 버튼 클릭
  4. 화면 지시에 따라 오브젝트 선택 및 옵션 입력
"""

import rhinoscriptsyntax as rs
import Rhino
import math


def create_star_points(center, outer_radius, inner_radius, num_points, angle_offset=0):
    """별 모양의 2D 꼭짓점 좌표 리스트를 반환합니다."""
    points = []
    total_verts = num_points * 2

    for i in range(total_verts):
        angle = math.radians(angle_offset + i * 180.0 / num_points)
        if i % 2 == 0:
            r = outer_radius
        else:
            r = inner_radius
        x = center.X + r * math.cos(angle)
        y = center.Y + r * math.sin(angle)
        z = center.Z
        points.append(Rhino.Geometry.Point3d(x, y, z))

    return points


def create_star_curve(center, outer_radius, inner_radius, num_points, plane, angle_offset=0):
    """지정한 평면(plane) 위에 별 모양 닫힌 폴리라인 커브를 생성합니다."""
    total_verts = num_points * 2
    pts = []

    for i in range(total_verts):
        angle = math.radians(angle_offset + i * 180.0 / num_points)
        r = outer_radius if i % 2 == 0 else inner_radius

        local_x = r * math.cos(angle)
        local_y = r * math.sin(angle)

        world_pt = plane.Origin + plane.XAxis * local_x + plane.YAxis * local_y
        pts.append(world_pt)

    pts.append(pts[0])  # 닫힌 커브
    polyline = Rhino.Geometry.Polyline(pts)
    return Rhino.Geometry.PolylineCurve(polyline)


def get_surface_domain(srf_obj):
    """Surface 또는 Brep의 UV 도메인과 법선 방향을 반환합니다."""
    brep = srf_obj.Geometry

    if isinstance(brep, Rhino.Geometry.Brep):
        face = brep.Faces[0]
        srf = face.UnderlyingSurface()
    elif isinstance(brep, Rhino.Geometry.Surface):
        srf = brep
    else:
        return None, None, None

    u_dom = srf.Domain(0)
    v_dom = srf.Domain(1)
    return srf, u_dom, v_dom


def main():
    rs.EnableRedraw(False)

    # ── 오브젝트 선택 ──────────────────────────────────────────────
    obj_id = rs.GetObject(
        "타공할 면(Surface) 또는 솔리드 오브젝트를 선택하세요",
        rs.filter.surface | rs.filter.polysurface
    )
    if not obj_id:
        print("오브젝트가 선택되지 않았습니다.")
        return

    # ── 타공 옵션 입력 ─────────────────────────────────────────────
    star_outer = rs.GetReal("별 외부 반지름 (mm)", 5.0, 1.0, 500.0)
    if star_outer is None:
        return

    star_inner = rs.GetReal("별 내부 반지름 (mm)", 2.0, 0.5, star_outer - 0.1)
    if star_inner is None:
        return

    num_points = rs.GetInteger("별 꼭짓점 개수", 5, 3, 12)
    if num_points is None:
        return

    spacing_x = rs.GetReal("X 방향 간격 (mm)", 20.0, star_outer * 2 + 1, 500.0)
    if spacing_x is None:
        return

    spacing_y = rs.GetReal("Y 방향 간격 (mm)", 20.0, star_outer * 2 + 1, 500.0)
    if spacing_y is None:
        return

    angle_offset = rs.GetReal("별 회전 각도 (도)", 90.0, -360.0, 360.0)
    if angle_offset is None:
        return

    # ── 오브젝트의 바운딩 박스로 배열 범위 계산 ────────────────────
    bbox = rs.BoundingBox(obj_id)
    if not bbox:
        print("바운딩 박스를 가져올 수 없습니다.")
        return

    min_pt = bbox[0]
    max_pt = bbox[6]

    obj_thickness = max_pt.Z - min_pt.Z
    extrude_depth = obj_thickness + 2.0  # 오브젝트를 완전히 관통하도록

    created_cutters = []

    x = min_pt.X + star_outer
    while x <= max_pt.X - star_outer:
        y = min_pt.Y + star_outer
        while y <= max_pt.Y - star_outer:
            # XY 평면 기준 별 커브 생성
            center = Rhino.Geometry.Point3d(x, y, min_pt.Z - 1.0)
            plane = Rhino.Geometry.Plane(center, Rhino.Geometry.Vector3d.ZAxis)

            star_curve = create_star_curve(
                center, star_outer, star_inner, num_points, plane, angle_offset
            )

            # 커브를 Z 방향으로 돌출(Extrude)하여 솔리드 커터 생성
            extrude_vec = Rhino.Geometry.Vector3d(0, 0, extrude_depth)
            extrude_path = Rhino.Geometry.Line(
                center,
                Rhino.Geometry.Point3d(center.X, center.Y, center.Z + extrude_depth)
            )

            extrusion = Rhino.Geometry.Surface.CreateExtrusion(star_curve, extrude_vec)
            if extrusion:
                brep = extrusion.ToBrep()
                capped = brep.CapPlanarHoles(Rhino.RhinoMath.ZeroTolerance)
                if capped:
                    brep = capped

                cutter_id = rs.AddBrep(brep)
                if cutter_id:
                    created_cutters.append(cutter_id)

            y += spacing_y
        x += spacing_x

    if not created_cutters:
        print("커터를 생성하지 못했습니다.")
        rs.EnableRedraw(True)
        return

    print("{}개의 별 모양 커터를 생성했습니다. Boolean Difference를 수행합니다...".format(len(created_cutters)))

    # ── Boolean Difference ─────────────────────────────────────────
    result = rs.BooleanDifference([obj_id], created_cutters, delete_input=True)

    rs.EnableRedraw(True)

    if result:
        print("완료! {}개의 별 모양 타공이 생성되었습니다.".format(len(created_cutters)))
        rs.SelectObjects(result)
    else:
        print("Boolean Difference 실패. 커터 오브젝트를 직접 확인하세요.")
        # 실패 시 커터를 남겨두어 디버깅 가능하게 함
        rs.SelectObjects(created_cutters)


if __name__ == "__main__":
    main()
