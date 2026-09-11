import React, { useId } from 'react';

export interface TooltipProps {
  content: string;
  children: React.ReactElement;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  position = 'top',
}) => {
  const tooltipId = useId();

  // Clone child element to inject aria-describedby for screenreaders
  const childWithAria = React.cloneElement(children, {
    'aria-describedby': tooltipId,
  });

  return (
    <div className={`tooltip-wrapper tooltip-wrapper--${position}`}>
      {childWithAria}
      <div id={tooltipId} role="tooltip" className="tooltip-bubble">
        {content}
      </div>
    </div>
  );
};
