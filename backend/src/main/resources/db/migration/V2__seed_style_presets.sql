-- Style presets. Spec: specs/05-editing-brain.md#b3-pacing-and-style-presets-pacingpy
-- Cut lengths are in beats per section. "auto" lets the director choose.

INSERT INTO style_preset (id, name, defaults) VALUES
    ('auto', 'Auto', '{}'),
    ('velocity', 'Velocity',
     '{"cutBeats":{"intro":2,"build":1,"drop":[0.5,1],"break":2,"outro":4},"fxIntensity":0.9,"grade":"Teal-orange, contrast"}'),
    ('hype', 'Hype',
     '{"cutBeats":{"intro":1,"build":0.5,"drop":0.5,"break":1,"outro":2},"fxIntensity":1.0,"grade":"Vibrant, glow"}'),
    ('cinematic', 'Cinematic',
     '{"cutBeats":{"intro":4,"build":2,"drop":2,"break":4,"outro":8},"fxIntensity":0.3,"grade":"Film LUT, grain, 2.39 bars"}'),
    ('anime', 'Anime-style',
     '{"cutBeats":{"intro":2,"build":1,"drop":0.5,"break":2,"outro":4},"fxIntensity":0.9,"grade":"Saturated, flashes, RGB split"}'),
    ('travel', 'Travel',
     '{"cutBeats":{"intro":4,"build":2,"drop":1,"break":4,"outro":4},"fxIntensity":0.5,"grade":"Warm, light leaks"}'),
    ('car', 'Car edit',
     '{"cutBeats":{"intro":2,"build":1,"drop":0.5,"break":2,"outro":4},"fxIntensity":0.8,"grade":"Moody, motion blur"}'),
    ('sports', 'Sports',
     '{"cutBeats":{"intro":2,"build":1,"drop":0.5,"break":2,"outro":4},"fxIntensity":0.8,"grade":"Punchy, high contrast"}');
