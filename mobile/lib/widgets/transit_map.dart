import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../config.dart';
import '../util/format.dart';

class MapLine {
  const MapLine(this.points, this.color);

  final List<LatLng> points;
  final Color color;
}

class MapStop {
  const MapStop(this.point, {this.selected = false});

  final LatLng point;
  final bool selected;
}

class MapBus {
  const MapBus(this.point, this.code, this.level, {this.dimmed = false});

  final LatLng point;
  final String code;
  final String? level; // null => "Məlumat yoxdur" (boz)
  final bool dimmed;
}

/// OpenStreetMap + görünən mənbə atribusiyası. Plitələr yüklənməsə də xəritənin üstündəki
/// xətt/dayanacaq/avtobus qatları (və tətbiqin qalan hissəsi) işləməyə davam edir.
class TransitMap extends StatelessWidget {
  const TransitMap({super.key, required this.lines, required this.stops, required this.buses});

  final List<MapLine> lines;
  final List<MapStop> stops;
  final List<MapBus> buses;

  static const LatLng _bakuCenter = LatLng(40.4093, 49.8671);

  @override
  Widget build(BuildContext context) {
    final all = <LatLng>[for (final l in lines) ...l.points, for (final s in stops) s.point];
    final bounds = all.length >= 2 ? LatLngBounds.fromPoints(all) : null;

    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: FlutterMap(
        options: MapOptions(
          initialCenter: all.isEmpty ? _bakuCenter : all.first,
          initialZoom: 13,
          initialCameraFit: bounds == null
              ? null
              : CameraFit.bounds(bounds: bounds, padding: const EdgeInsets.all(28)),
        ),
        children: [
          TileLayer(
            urlTemplate: AppConfig.osmTileUrl,
            userAgentPackageName: AppConfig.tileUserAgent,
          ),
          PolylineLayer(
            polylines: [
              for (final l in lines) Polyline(points: l.points, strokeWidth: 3.5, color: l.color),
            ],
          ),
          MarkerLayer(
            markers: [
              for (final s in stops)
                Marker(
                  point: s.point,
                  width: s.selected ? 30 : 14,
                  height: s.selected ? 30 : 14,
                  child: s.selected
                      ? const Icon(Icons.location_on, color: Color(0xFF0B5FA5), size: 30)
                      : Container(
                          decoration: BoxDecoration(
                            color: Colors.white,
                            shape: BoxShape.circle,
                            border: Border.all(color: const Color(0xFF455A64), width: 2),
                          ),
                        ),
                ),
            ],
          ),
          MarkerLayer(
            markers: [
              for (final b in buses)
                Marker(
                  point: b.point,
                  width: 58,
                  height: 46,
                  child: _BusMarker(bus: b),
                ),
            ],
          ),
          RichAttributionWidget(
            attributions: [
              TextSourceAttribution('OpenStreetMap contributors'),
            ],
          ),
        ],
      ),
    );
  }
}

class _BusMarker extends StatelessWidget {
  const _BusMarker({required this.bus});

  final MapBus bus;

  @override
  Widget build(BuildContext context) {
    final color = crowdColor(bus.level);
    final short = bus.code.replaceFirst('DEMO-', '');
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: bus.dimmed ? const Color(0xFF9E9E9E) : color,
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white, width: 2),
          ),
          child: const Icon(Icons.directions_bus, size: 16, color: Colors.white),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(4)),
          child: Text(short, style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700)),
        ),
      ],
    );
  }
}
