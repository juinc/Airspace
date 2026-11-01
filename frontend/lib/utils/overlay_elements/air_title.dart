import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AirTitle extends StatelessWidget {
  const AirTitle({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(10),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.2),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Image.asset(
            'assets/pictures/image.png',
            width: 22,
            height: 22,
            fit: BoxFit.contain,
          ),
        ),

        const SizedBox(width: 10),

        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Airspace',
              style: GoogleFonts.playwriteItTrad(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w900,
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