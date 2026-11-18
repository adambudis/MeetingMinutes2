import LinearProgress from '@mui/material/LinearProgress';
import { useEffect, useState } from 'react';

interface Props {
  active: boolean;
  getLevel: () => number;
}

/** Microphone level bar; polls the recorder ~20x per second while recording. */
export function VuMeter({ active, getLevel }: Props) {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!active) {
      setLevel(0);
      return;
    }
    let frame = 0;
    let last = 0;
    const tick = (time: number) => {
      if (time - last >= 50) {
        last = time;
        setLevel(getLevel());
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, getLevel]);

  return (
    <LinearProgress
      variant="determinate"
      value={level * 100}
      aria-label="Hlasitost mikrofonu"
      sx={{ flex: 1, height: 12, borderRadius: 1, '& .MuiLinearProgress-bar': { transition: 'none' } }}
    />
  );
}
