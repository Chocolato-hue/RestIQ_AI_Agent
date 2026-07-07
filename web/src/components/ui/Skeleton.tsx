import React from 'react';
import styles from './Skeleton.module.css';

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  variant?: 'text' | 'rect' | 'circle';
  className?: string;
}

export default function Skeleton({
  width,
  height,
  borderRadius,
  variant = 'rect',
  className = '',
}: SkeletonProps) {
  const classes = [styles.skeleton, styles[variant], className].filter(Boolean).join(' ');

  const inlineStyle: React.CSSProperties = {
    width,
    height,
    borderRadius,
  };

  return <div className={classes} style={inlineStyle} />;
}
