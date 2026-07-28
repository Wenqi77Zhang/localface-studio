# Public synthetic benchmark provenance

## synthetic-01-single-frontal

- Created: 2026-07-28
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic face-detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- SHA-256: `2d3d6c7dea56f9d67334c57207112f4fc4878815d3fe3de123f137a920351b1d`
- Manual ground-truth review: one visible frontal face; normalized box reviewed against the image rather than copied directly from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult person facing the camera for a baseline face-detection test
Scene/backdrop: plain neutral light-gray indoor wall with subtle natural texture
Subject: one fictional adult, shoulders and full head visible, centered, looking directly at camera, neutral relaxed expression, both eyes visible, no glasses, no hat, no facial occlusion
Style/medium: photorealistic natural camera photograph with realistic skin and hair texture; clearly synthetic and not based on any real or famous person
Composition/framing: landscape 3:2 frame, eye-level medium close-up, exactly one person, generous margin around the full head, face occupies roughly 25 percent of image width
Lighting/mood: soft even daylight, normal exposure, low shadow, natural color
Constraints: exactly one face; no other people; no mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-02-three-frontal

- Created: 2026-07-28
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic multi-face detection engineering benchmark
- Real-person reference images: none
- Claimed identities: none; all subjects are specified as fictional
- Final encoding: lossless WebP; decoded RGB pixels were verified identical to the generated PNG
- SHA-256: `ed2b0a09746706aebcfd0cc49d3a68e66b37c06f16b62ffb1a563eceba779927`
- Manual ground-truth review: three visible frontal faces; normalized boxes were reviewed against the image rather than copied directly from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional small group of adults for a multi-face detection test
Scene/backdrop: plain neutral indoor studio wall with subtle natural texture and no decorations
Subject: exactly three fictional adults standing in one row, separated with visible space between heads, all looking toward the camera, neutral relaxed expressions, all eyes visible, no glasses, no hats, no facial occlusion; visibly distinct faces and hairstyles; not based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic skin, hair, and everyday fabric texture; clearly synthetic
Composition/framing: landscape 3:2 frame, eye-level waist-up group portrait, all three full heads entirely visible with generous margin, faces at comparable medium size, no overlapping faces
Lighting/mood: soft even daylight, normal exposure, low shadow, natural color
Constraints: exactly three people and exactly three visible faces; no additional people; no mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-03-small-distant

- Created: 2026-07-28
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic small-face detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: JPEG quality 95 with 4:4:4 chroma sampling, selected to satisfy the public repository size gate while retaining the original 1536 by 1024 dimensions
- SHA-256: `582870364379a3d8b58b882437cae861592cf722c37956398387364db3d75090`
- Manual ground-truth review: one visible distant face measuring approximately 24 by 32 pixels; the normalized box was reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult appearing small in a wide outdoor scene for a small-face detection test
Scene/backdrop: spacious quiet public park with lawn, a few ordinary trees, and a simple distant path; no signs, posters, statues, or crowds
Subject: exactly one fictional adult standing far from the camera near the center, facing the camera, full body visible, neutral posture, unobstructed face; not based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic vegetation, clothing, and atmospheric depth; clearly synthetic
Composition/framing: landscape 3:2 wide establishing shot, eye level, subject occupies about 8 percent of image height and the face is small but still visibly human, generous surroundings, no other people
Lighting/mood: soft overcast daylight, normal exposure, natural color, moderate background detail
Constraints: exactly one person and one face; face fully visible; no additional people; no mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective small-face detector evaluation; no beauty retouching
```

## synthetic-04-profile-occluded

- Created: 2026-07-28
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic profile and partial-occlusion detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: losslessly optimized PNG
- SHA-256: `a0720823041d7d0142e1e87423a7b8009a425776e4b13de525f2ba4d284e8187`
- Manual ground-truth review: one visible profile face with controlled lower-face occlusion; the normalized box was reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult in side profile with controlled partial facial occlusion for a difficult face-detection test
Scene/backdrop: simple neutral indoor room with a plain muted wall and no decorations
Subject: exactly one fictional adult shown from shoulders up in a clear three-quarter-to-side profile, head turned about 65 degrees away from the camera; one hand naturally raised so two fingers cover a small part of the lower cheek and mouth while the eye, nose bridge, forehead, and most facial outline remain visible; no glasses, no hat; not based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic skin, hair, hand anatomy, and fabric texture; clearly synthetic
Composition/framing: landscape 3:2 frame, eye-level medium close-up, full head and raised hand fully inside the frame, generous margin, exactly one visible face
Lighting/mood: soft side daylight with moderate contrast, correct exposure, natural color
Constraints: exactly one person; controlled partial occlusion only; do not cover the whole face; no additional people; no mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-05-rotated

- Created: 2026-07-28
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic in-plane rotation face-detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: lossless WebP; decoded RGB pixels were verified identical to the generated PNG
- SHA-256: `19017080b933ee14298963667fff22778bef6ebbe98cb3223d68eee735ae3256`
- Manual ground-truth review: one visible frontal face rotated approximately 40 degrees in the image plane; the normalized box was reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult photographed with strong in-plane face rotation for a difficult face-detection test
Scene/backdrop: plain neutral indoor wall with subtle texture and no decorations
Subject: exactly one fictional adult, shoulders and full head visible, looking at the camera with a neutral expression, both eyes visible, no glasses, no hat, no facial occlusion; the person's head and shoulders are tilted about 40 degrees clockwise within the image while the face remains frontal; not based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic skin, hair, and fabric texture; clearly synthetic
Composition/framing: landscape 3:2 frame, medium close-up, eye-level camera, full rotated head entirely inside the frame with generous margin, face occupies roughly 25 percent of image width
Lighting/mood: soft even daylight, normal exposure, natural color
Constraints: exactly one person and one face; preserve obvious 40-degree in-plane rotation; no additional people; no mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-06-backlit

- Created: 2026-07-29
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic backlit face-detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: losslessly optimized PNG
- SHA-256: `6c2b2cc4fc460257affb7a0685e8a8bf5599fb01a1fcff9883d65f700b97a2cc`
- Manual ground-truth review: one visible frontal face under strong backlighting; the normalized box was reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult under strong backlighting for a difficult face-detection test
Scene/backdrop: simple indoor room facing a large bright window with no visible signs, reflections, portraits, or other people
Subject: exactly one fictional adult, shoulders and full head visible, facing the camera with a neutral expression, both eyes visible, no glasses, no hat, no facial occlusion; facial features remain faintly but clearly visible despite the bright background; not based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic skin, hair, fabric, highlight roll-off, and mild sensor noise; clearly synthetic
Composition/framing: landscape 3:2 frame, eye-level medium close-up, full head entirely inside the frame with generous margin, face occupies roughly 22 percent of image width
Lighting/mood: very bright window directly behind the subject, underexposed face with preserved shadow detail, strong dynamic range, natural color, no artificial fill flash
Constraints: exactly one person and one face; strong backlight must be visually obvious while the face remains human-reviewable; no additional people; no mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-07-low-light

- Created: 2026-07-29
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic low-light face-detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: lossless WebP; decoded RGB pixels were verified identical to the generated PNG
- SHA-256: `f19948d2ab20d72ab3cc18490431502a19935c778096f5a8f9c7d75b7973c8e7`
- Manual ground-truth review: one visible frontal face under dim uneven illumination; the normalized box was reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult in a genuinely dim indoor environment for a low-light face-detection test
Scene/backdrop: sparse dark room at night with a plain wall, no windows, decorations, screens, or reflective surfaces
Subject: exactly one fictional adult, shoulders and full head visible, facing the camera with a neutral expression, both eyes visible, no glasses, no hat, no facial occlusion; facial outline and core features remain human-reviewable in the darkness; not based on any real or famous person
Style/medium: photorealistic natural high-ISO camera photograph with realistic skin and hair, visible fine sensor noise, slightly reduced color saturation, and no cinematic glamour; clearly synthetic
Composition/framing: landscape 3:2 frame, eye-level medium close-up, full head entirely inside the frame with generous margin, face occupies roughly 24 percent of image width
Lighting/mood: one weak warm household lamp off camera, low overall exposure, deep but not crushed shadows, uneven illumination across the face, realistic nighttime color
Constraints: exactly one person and one face; scene must remain visibly low-light rather than brightened to normal exposure; no additional people; no mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-08-motion-blur

- Created: 2026-07-29
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic motion-blur face-detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: losslessly optimized PNG
- SHA-256: `91d58a3a587f3a801b7d9d0e42f6854b051c3bd21db134c20058c4dcd3e45309`
- Manual ground-truth review: one visible face under directional motion blur; the normalized box was reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult captured with moderate motion blur for a difficult face-detection test
Scene/backdrop: plain neutral indoor corridor with no signs, posters, mirrors, screens, or other people
Subject: exactly one fictional adult walking laterally while turning the face toward the camera, shoulders and full head visible, neutral expression, no glasses, no hat, no facial occlusion; not based on any real or famous person
Style/medium: photorealistic natural handheld camera photograph with realistic skin, hair, fabric, and directional motion blur; clearly synthetic
Composition/framing: landscape 3:2 frame, eye-level medium close-up, full head entirely inside the frame with generous margin, face occupies roughly 22 percent of image width
Lighting/mood: ordinary even indoor light, normal exposure, natural color
Constraints: exactly one person and one visible face; apply moderate directional motion blur across the face and body while facial location and outline remain human-reviewable; do not create a sharp frozen face; no additional people, reflections, portraits, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-09-edge-cropped

- Created: 2026-07-29
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic edge-cropped face-detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: losslessly optimized PNG
- SHA-256: `e1b9dddc04a5933d1e40701f06c261328ed82520d3063f858dd1f404c8459265`
- Manual ground-truth review: one face whose outer portion is cropped by the left image boundary; the normalized box was reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult whose face is intentionally positioned at the extreme image edge and partially cropped for a difficult face-detection test
Scene/backdrop: plain neutral indoor wall with subtle natural texture and no decorations
Subject: exactly one fictional adult facing the camera with a neutral expression, both eyes visible before the frame crop, no glasses, no hat, no facial occlusion; the left edge of the image cuts through the outer quarter of the person's head and one ear, while most of the face including both eyes, nose, and mouth remains visible; not based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic skin, hair, and fabric texture; clearly synthetic
Composition/framing: landscape 3:2 frame, eye-level close-up, face placed flush against the left image boundary, intentional partial head crop only at that boundary, no other subjects
Lighting/mood: soft even daylight, normal exposure, natural color
Constraints: exactly one person and one visible face; make the left-boundary crop unambiguous but retain enough face for human ground-truth review; no additional people, mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-10-back-view-negative

- Created: 2026-07-29
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic negative control for face-detector false-positive evaluation
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: losslessly optimized PNG
- SHA-256: `66888801241017bda39d3eb376e9c0f28755f27668541101de9e52837c8e06f6`
- Manual ground-truth review: one person is present but no face or facial profile is visible; the ground-truth face array is intentionally empty

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic negative-control benchmark image for face detection
Primary request: a completely fictional adult seen strictly from behind so that no face is visible
Scene/backdrop: simple quiet outdoor path with plain greenery and shallow natural depth of field; no crowds, signs, statues, posters, or buildings with face-like patterns
Subject: exactly one fictional adult shown from shoulders up, centered, back of head toward the camera, looking directly away; only hair, back of ears, neck, and shoulders visible; absolutely no eyes, nose, mouth, facial profile, reflection, or partial face; not based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic hair, fabric, and vegetation texture; clearly synthetic
Composition/framing: landscape 3:2 frame, eye-level rear portrait, full back of head inside the frame with generous margin
Lighting/mood: soft even overcast daylight, normal exposure, natural color
Constraints: exactly one person but zero visible faces; no additional people; no mirrors, reflective surfaces, portraits, screens, mannequins, masks, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable as a negative control for objective face-detector false-positive evaluation
```

## synthetic-11-glasses-cap

- Created: 2026-07-29
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic accessory-interference face-detection engineering benchmark
- Real-person reference images: none
- Claimed identity: none; the subject is specified as fictional
- Final encoding: losslessly optimized PNG
- SHA-256: `d73f8419ec88490ac4015298e07061aa4829690b6eed478fd70b396e76e2735e`
- Manual ground-truth review: one visible frontal face with clear glasses and a cap-brim shadow; the normalized box was reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic face-detection benchmark image
Primary request: a completely fictional adult wearing common accessories that create controlled facial interference for a face-detection test
Scene/backdrop: plain neutral outdoor wall with subtle natural texture and no decorations
Subject: exactly one fictional adult facing the camera with a neutral expression, wearing ordinary clear-lens eyeglasses with visible frames and a plain brimmed cap; the cap brim casts a moderate shadow across the forehead and upper eye area, but both eyes, nose, mouth, and facial outline remain human-reviewable; no scarf or mask; not based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic skin, hair, transparent lens reflections, fabric, and cap texture; clearly synthetic
Composition/framing: landscape 3:2 frame, eye-level medium close-up, shoulders and full head including cap entirely inside the frame with generous margin, face occupies roughly 24 percent of image width
Lighting/mood: directional afternoon daylight, moderate cap-brim shadow, correct exposure, natural color
Constraints: exactly one person and one visible face; glasses must have clear lenses rather than dark sunglasses; cap must be plain with no writing or logo; no additional people, mirrors, portraits, screens, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective face-detector evaluation; no beauty retouching
```

## synthetic-12-mixed-scale-four

- Created: 2026-07-29
- Generator path: Codex built-in `image_gen`
- Intended use: public synthetic mixed-scale multi-face detection engineering benchmark
- Real-person reference images: none
- Claimed identities: none; all subjects are specified as fictional
- Final encoding: losslessly optimized PNG
- SHA-256: `e0dff1af0c0804660820023bffa3572b60c781368a6926e744acf7b4e49485cc`
- Manual ground-truth review: four visible frontal faces at different perspective scales; normalized boxes were reviewed against the image rather than copied from detector output

Prompt:

```text
Use case: photorealistic-natural
Asset type: public synthetic multi-face detection benchmark image
Primary request: exactly four completely fictional adults positioned at clearly different distances from the camera for a mixed-scale multi-face detection test
Scene/backdrop: spacious plain indoor hall with visible depth, neutral walls, and no signs, posters, mirrors, screens, or decorations
Subject: exactly four fictional adults, all facing the camera with neutral expressions and unobstructed faces, no glasses, no hats; one person in the foreground with a large face, two people at middle distance with medium faces, and one person farther back with a small but human-reviewable face; faces and bodies do not overlap; none is based on any real or famous person
Style/medium: photorealistic natural camera photograph with realistic skin, hair, everyday clothing, perspective, and depth; clearly synthetic
Composition/framing: landscape 3:2 wide frame, eye-level view, all four full heads inside the frame, substantial horizontal separation between faces, perspective scale differences are obvious
Lighting/mood: soft even indoor daylight, normal exposure, natural color, enough depth of field for all four faces to remain reviewable
Constraints: exactly four people and exactly four visible faces; no extra people or partial background figures; no overlapping faces; no mirrors, portraits, screens, mannequins, face-like objects, logos, text, captions, borders, signatures, or watermark; suitable for objective mixed-scale face-detector evaluation; no beauty retouching
```
