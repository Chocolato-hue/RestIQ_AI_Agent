import React from 'react';
import Link from 'next/link';
import styles from './GradientButton.module.css';

interface GradientButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  href?: string;
  variant?: 'primary' | 'secondary' | 'glass';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  type?: 'button' | 'submit' | 'reset';
  className?: string;
}

export default function GradientButton({
  children,
  onClick,
  href,
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  type = 'button',
  className = '',
}: GradientButtonProps) {
  const classes = [
    styles.btn,
    styles[variant],
    styles[size],
    fullWidth ? styles.fullWidth : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  if (href) {
    return (
      <Link href={href} className={classes} onClick={onClick}>
        <span className={styles.inner}>{children}</span>
      </Link>
    );
  }

  return (
    <button type={type} className={classes} onClick={onClick}>
      <span className={styles.inner}>{children}</span>
    </button>
  );
}
