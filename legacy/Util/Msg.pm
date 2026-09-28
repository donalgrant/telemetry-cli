package Util::Msg;

=head1 

Util::Msg - A module for easy diagnostic messaging

=cut

use strict;
use warnings;
use Text::Wrap;

BEGIN {
  use Exporter ();
  our ($VERSION, @ISA, @EXPORT, @EXPORT_OK, %EXPORT_TAGS);

  $VERSION = 1.00;
  @ISA = qw(Exporter);
  @EXPORT = qw(&msg 
	       &msg_report 
	       &msg_output
	       &msg_tag_counts &msg_clr_counts
	       &msg_tag_default
	       &msg_set_opt &msg_clr_opt 
	       &msg_set_lvl &msg_clr_lvl
	       &msg_set_wrap &msg_clr_wrap
	       &msg_only_tags &msg_hide_tags &msg_all_tags);
  %EXPORT_TAGS = ( );

  @EXPORT_OK = qw( );
}
our @EXPORT_OK;

our @MSG_FH= ( *STDOUT ) ;  # by default, send messages to STDOUT

our $MSG_NUMBER=0;
our %TAG_COUNT;
our %OPT;
our %ONLY_TAGS;
our %HIDE_TAGS;
our $TAG_DELIM=' ';
our $MSG_WRAP=0;           # no wrapping by default

our $ONLY_TAGS=0;
our $HIDE_TAGS=0;
our $LVL_TAGS=0;
our $DEFAULT_TAG='NOTE';

our $LVL=0;

sub msg_output  { @MSG_FH=@_ }
sub msg_set_opt { for (@_) { $OPT{$_}=1 } }
sub msg_clr_opt { for (@_) { $OPT{$_}=0 } }
sub msg_set_lvl { $LVL=shift; $LVL_TAGS=1 }
sub msg_clr_lvl { $LVL_TAGS=0 }

sub msg_set_wrap { $MSG_WRAP=shift() }   
sub msg_clr_wrap { $MSG_WRAP=0 }

sub msg_tag_default { $DEFAULT_TAG=shift }

sub msg_only_tags { 
  return unless scalar(@_);
  for (@_) { $ONLY_TAGS{$_}=1 } 
  $ONLY_TAGS=1;
}

sub msg_hide_tags {
  return unless scalar(@_);
  for (@_) { $HIDE_TAGS{$_}=1 }
  $HIDE_TAGS=1;
}

sub msg_all_tags { $ONLY_TAGS=$HIDE_TAGS=0; %ONLY_TAGS=(); %HIDE_TAGS=() }

sub msg {
  my $m=shift // '';
  my $tag=shift;
  my $tag_is_numeric = (defined $tag && $tag=~/^\d+$/) ? 1 : 0;
  return if ($LVL_TAGS) && (defined $tag) && $tag_is_numeric && ($tag > $LVL);
  $tag="LVL$tag" if $tag_is_numeric;
  $tag //= $DEFAULT_TAG;
  if ($ONLY_TAGS) { return unless $ONLY_TAGS{$tag} }
  if ($HIDE_TAGS) { return if     $HIDE_TAGS{$tag} }
  if ($MSG_WRAP) {
    $Text::Wrap::columns=$MSG_WRAP;
    $m=wrap("","",$m);
  }
  my @o;  # output lines
  if ($OPT{TAG_MULTILINE}) { @o=split("\n",$m) }
  else                     { $o[0]=$m }
  $TAG_COUNT{$tag}++;
  $MSG_NUMBER++;
  $tag=$tag.'-'.$TAG_COUNT{$tag} if $OPT{TAG_NUMBERS};
  $tag=sprintf('%04d',$MSG_NUMBER).' '.$tag if $OPT{MSG_NUMBERS};
  $tag.=' '.localtime() if $OPT{TIME_TAGS};
  if ($OPT{CALLER}) {
    my @c=caller(1);
    $tag.=sprintf(' %05d',$c[2])."_$c[3]";
  }
  for my $fh (@MSG_FH) {
    for my $o (@o) { print $fh $tag,$TAG_DELIM,$o,"\n" }
  }
}

sub msg_report {
  my $tag=shift() // $DEFAULT_TAG;
  msg "MSG Report:\n".join('',map { sprintf("\%5d $_ message(s)\n",$TAG_COUNT{$_}) } sort keys %TAG_COUNT), $tag;
}

sub msg_clr_counts { %TAG_COUNT=() }
sub msg_tag_counts { return %TAG_COUNT }

END { }

=head1 SYNOPSIS

  use Util::Msg;
  
  msg "This is a diagnostic message with the default tag (NOTE)";
  msg "This is a warning message", 'WARN';
  
  msg_set_lvl(2);  # ignore messages of level higher than '2'
  msg_tag_default('#');  # change default tag from 'NOTE' to '#'

  msg "Hello, World - 1", 1;
  msg "Hello, World - 2", 2;
  msg "Hello, World - 3", 3;  # ignored
  
  msg_clr_lvl;                # no longer do "level"-checking
  msg "Hello, World - 3", 3;  # not ignored
  
  msg_only_tags qw(WARN FAIL);  # only show WARN and FAIL tagged-messages
  
  msg "Note message";           # ignored
  msg "WARN message", 'WARN';   # displayed
  msg "warn message", 'warn';   # ignored -- case-sensitive
  msg "FAIL message", 'FAIL';   # displayed
  
  msg_hide_tags qw(WARN);       # explicitly exclude messages with "WARN" tag
  
  msg "Another WARN Message", 'WARN';  # ignored
  msg "Another FAIL Message", 'FAIL';  # still displayed
  
  msg_all_tags;                 # no filtering on tags
  
  msg_set_opt qw( MSG_NUMBERS TAG_MULTILINE TIME_TAGS TAG_NUMBERS );  # some options (see OPTIONS in Util::Msg pod)
  
  msg "Last WARN Message", 'WARN';  # shown with number of the message, number of the WARN-tag, time-tag
  
  my %T = msg_tag_counts;           # get hash with tag-counts     
  use Data::Dumper;
  msg Dumper(\%T);                  # Dumper multi-line output displayed with tags on each line
  
  msg_report;                       # formatted report for tag-counts
  msg_clr_counts;                   # reset tag-counts to zero for all tags
  msg_clr_opt qw( TIME_TAGS );      # don't do time-tagging of messages

  my $fh;  
  open $fh, '>>', 'msg.log' or die "Couldn't open logfile for append:  $!";

  msg_output( *STDOUT, $fh );       # send output to both STDOUT and msg.log
  for (1..5) { msg "message $_" }   # output written to STDOUT and msg.log

  msg_report;                       # updated tag-count report, now with only five (not 10) '#' messages

  msg_set_wrap(20);                 # messages of approx 20 chars per line (not including tags, time, and numbering)
  msg "And this is a really long line which we will check for line-wrapping"x20;  # should be broken into several lines

=cut

=head1 DESCRIPTION

  msg keeps track of the number of messages of each 'tag' type
  
  msg also allows a "level" of message detail.  By default,
  all messages are level 0, and will not be filtered.  However
  if msg_set_lvl gets an argument > 0, then only messages with a
  level less than or equal to that argument will be displayed.
  
  msg allows filtering on the tags, so certain tags can be
  hidden, and also only certain tags can be specified for display
  
=head1 OPTIONS

  There is a facility for specifying options:
  Available options include:
  
=over 4

=item MSG_NUMBERS

Display an output line number in front of all Msg output.

=item TAG_NUMBERS

For each kind of tag, append the number of the tag-message.
Multiline output messages will share the same number for a given call to msg.  

=item TAG_MULTILINE

Prefix each line of a multiline msg with the tag info for that message

=item TIME_TAGS

Include the date-time string (localtime) as a prefix

=item CALLER

Include info from a call to caller(1)

=back
                     
=head1 TODO

  Still need to handle output better -- don't just use STDOUT,
  and possibly allow parallel writing to a logfile and STDOUT.
  (Perhaps allow a list of filehandles to be passed as an option?)

=cut

1;  # must return true from a module
