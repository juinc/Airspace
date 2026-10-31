import 'package:flutter/material.dart';

class AirTitle extends StatelessWidget {
  const AirTitle({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Icon badge
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: const Color.fromARGB(255, 165, 47, 139),
            borderRadius: BorderRadius.circular(10),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.2),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Transform.rotate(
            angle: 0.9,
            child: const Icon(
              Icons.send_rounded,
              color: Color(0xFFFFE306),
              size: 22,
            ),
          ),
        ),

        const SizedBox(width: 10),

        // Wordmark
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Airspace',
              style: TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w900,
                letterSpacing: 3,
                height: 1,
              ),
            ),
            Container(
              margin: const EdgeInsets.only(top: 2),
              width: 100,
              height: 2,
              color: const Color.fromARGB(255, 21, 83, 153)
                  .withValues(alpha: 0.6),
            ),
          ],
        ),
      ],
    );
  }
}