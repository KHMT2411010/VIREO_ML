(() => {
  'use strict';

  const canvas = document.querySelector('#collision-ribbons');
  const stage = canvas?.closest('.stage');
  const ctx = canvas?.getContext('2d');
  if (!stage || !ctx) return;

  const TAU = 2 * Math.PI;
  const samples = 80;
  const fiberCount = 25;
  const ribbons = [
    { height: .58, amplitude: .23, phase: .92, width: .147, strength: 1, speed: 1.12 },
    { height: .70, amplitude: .20, phase: 2.28, width: .114, strength: .77, speed: .94 },
    { height: .43, amplitude: .17, phase: 1.62, width: .088, strength: .58, speed: .83 },
    { height: .76, amplitude: .13, phase: 3.35, width: .064, strength: .43, speed: .79 },
    { height: .36, amplitude: .18, phase: 4.12, width: .060, strength: .37, speed: .72 },
  ].map(ribbon => ({
    ...ribbon,
    fibers: Array.from({ length: fiberCount }, (_, index) => ({
      offset: 2 * index / (fiberCount - 1) - 1,
      phase: Math.random() * TAU,
      speed: .24 + Math.random() * .48,
      bend: .006 + Math.random() * .012,
      opacity: .45 + Math.random() * .55,
    })),
    center: new Float32Array(samples + 1),
    spread: new Float32Array(samples + 1),
  }));

  let width = 0;
  let height = 0;
  let time = 0;
  let previous;
  let animation = 0;

  function resize() {
    const bounds = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = bounds.width;
    height = bounds.height;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    render();
  }

  function trace(ribbon, offset, reverse = false) {
    for (let step = 0; step <= samples; step++) {
      const index = reverse ? samples - step : step;
      const x = width * index / samples;
      const y = ribbon.center[index] + ribbon.spread[index] * offset;
      if (step === 0 && !reverse) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
  }

  function drawRibbon(ribbon, index) {
    const motion = time * ribbon.speed;
    for (let step = 0; step <= samples; step++) {
      const x = step / samples;
      const phase = x * 7.1 - motion + ribbon.phase;
      ribbon.center[step] = height * (
        ribbon.height + ribbon.amplitude * Math.sin(phase) +
        .043 * Math.sin(phase * 1.91 + time * .24) +
        .031 * Math.sin(x * 10 + time * .49)
      );
      ribbon.spread[step] = height * ribbon.width *
        (.22 + .78 * Math.abs(Math.sin(phase * .75 + index * .6))) *
        Math.pow(1 - x * .84, .58);
    }

    // The highlight crosses the visible section, then wraps outside the canvas.
    const head = ((time * (.27 + index * .019) + .42 + index * .29) % 1.34) - .24;
    const fill = ctx.createLinearGradient(0, 0, width, 0);
    for (let step = 0; step <= 24; step++) {
      const x = step / 24;
      const light = Math.exp(-Math.pow((x - head) / .108, 2));
      const alpha = ribbon.strength * (.20 + .38 * light) * (1 - .47 * x);
      fill.addColorStop(x, `rgba(83, 218, 118, ${alpha})`);
    }
    ctx.beginPath();
    trace(ribbon, 1);
    trace(ribbon, -1, true);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();

    const threads = ctx.createLinearGradient(0, 0, width, 0);
    for (let step = 0; step <= 32; step++) {
      const x = step / 32;
      const light = Math.exp(-Math.pow((x - head) / .064, 2));
      const alpha = ribbon.strength * (.28 + .71 * light) * (1 - .47 * x);
      threads.addColorStop(x, `rgba(${108 + Math.round(light * 126)}, 255, ${121 + Math.round(light * 31)}, ${alpha})`);
    }
    ctx.strokeStyle = threads;

    for (const fiber of ribbon.fibers) {
      ctx.beginPath();
      for (let step = 0; step <= samples; step++) {
        const x = step / samples;
        const flare = Math.sin(x * 8 + time * fiber.speed + fiber.phase);
        const ripple = Math.sin(x * 15 - time * .41 + fiber.phase);
        const bend = height * fiber.bend * (.75 * flare + .25 * ripple);
        const y = ribbon.center[step] + ribbon.spread[step] * fiber.offset + bend;
        if (step === 0) ctx.moveTo(0, y);
        else ctx.lineTo(x * width, y);
      }
      ctx.globalAlpha = fiber.opacity * (.75 + .25 * Math.abs(fiber.offset));
      ctx.lineWidth = Math.abs(fiber.offset) > .8 ? 1.2 : .68;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // Light catches the folded edge while the fine interior threads keep flowing.
    const edge = ctx.createLinearGradient(0, 0, width, 0);
    for (let step = 0; step <= 40; step++) {
      const x = step / 40;
      const highlight = Math.exp(-Math.pow((x - head) / .082, 2));
      const alpha = ribbon.strength * (.38 + .61 * highlight) * (1 - .38 * x);
      edge.addColorStop(x, `rgba(${145 + Math.round(105 * highlight)}, 255, 159, ${alpha})`);
    }
    ctx.beginPath();
    trace(ribbon, -1);
    ctx.strokeStyle = edge;
    ctx.lineWidth = index === 0 ? 2.5 : 1.55;
    ctx.stroke();

    if (head <= 0 || head >= .91 || index >= 3) return;
    const x = width * head;
    const sample = head * samples;
    const left = Math.floor(sample);
    const fraction = sample - left;
    const y = (ribbon.center[left] - ribbon.spread[left]) * (1 - fraction) +
      (ribbon.center[left + 1] - ribbon.spread[left + 1]) * fraction;
    const radius = Math.max(20, height * .21);
    const fade = Math.min(1, head * 16, (.91 - head) * 6);
    const glow = ctx.createRadialGradient(x, y, 0, x, y, radius);
    glow.addColorStop(0, `rgba(220, 255, 144, ${.70 * fade * ribbon.strength})`);
    glow.addColorStop(.23, `rgba(133, 249, 98, ${.32 * fade * ribbon.strength})`);
    glow.addColorStop(1, 'rgba(101, 236, 95, 0)');
    ctx.fillStyle = glow;
    ctx.fillRect(x - radius, y - radius, 2 * radius, 2 * radius);
  }

  function render() {
    if (!width || !height) return;
    ctx.clearRect(0, 0, width, height);
    ribbons.forEach(drawRibbon);
  }

  function frame(now) {
    if (previous !== undefined) time += Math.min((now - previous) / 1000, .05);
    previous = now;
    render();
    animation = requestAnimationFrame(frame);
  }

  function syncPlayback() {
    cancelAnimationFrame(animation);
    previous = undefined;
    if (!document.hidden && !stage.classList.contains('motion-paused')) {
      animation = requestAnimationFrame(frame);
    } else {
      render();
    }
  }

  new ResizeObserver(resize).observe(canvas);
  new MutationObserver(syncPlayback).observe(stage, {
    attributes: true,
    attributeFilter: ['class'],
  });
  document.addEventListener('visibilitychange', syncPlayback);
  resize();
  syncPlayback();
})();
